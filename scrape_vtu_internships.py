#!/usr/bin/env python3
"""
VTU InternYet internships scraper

Usage examples:
  python scrape_vtu_internships.py --url "https://vtuinternyet.in/browse-internships" --headless
  python scrape_vtu_internships.py --max-pages 3 --keyword python

Outputs: `vtu_internships.csv` (and optional JSON)
"""
import argparse
import json
import logging
import sys
import time
from typing import List, Dict, Optional

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def create_driver(headless: bool = True, window_size: str = "1920,1080") -> webdriver.Chrome:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    # Common flags that improve stability inside containers
    chrome_options.add_argument(f"--window-size={window_size}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--remote-debugging-port=9222")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def get_text_safe(parent, css: Optional[str] = None, xpath: Optional[str] = None) -> str:
    try:
        if css:
            el = parent.find_element(By.CSS_SELECTOR, css)
            return el.text.strip()
    except Exception:
        pass
    try:
        if xpath:
            el = parent.find_element(By.XPATH, xpath)
            return el.text.strip()
    except Exception:
        pass
    return ""


def wait_for_visible(driver, by, selector, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, selector)))
    except TimeoutException:
        return None


def scrape_cards_on_page(driver, keyword: Optional[str] = None) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    possible_card_selectors = [
        "div[class*='shadow']",
        "div.card",
        "article",
        "div.internship-card",
        "div[class*='internship']",
    ]

    cards = []
    for sel in possible_card_selectors:
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break
        except Exception:
            continue

    if not cards:
        try:
            cards = driver.find_elements(By.XPATH, "//div[.//a or .//h2 or .//h3]")
        except Exception:
            cards = []

    logging.info("Found %d potential card elements on page", len(cards))

    for card in cards:
        title = get_text_safe(card, css="h2", xpath=".//h2|.//h3|.//a[@class='title']")
        company = get_text_safe(card, css=".company, .company-name", xpath=".//p[contains(@class,'company')]|.//div[contains(@class,'company')]")
        location = get_text_safe(card, css=".location", xpath=".//span[contains(@class,'location')]")
        mode = get_text_safe(card, css=".mode", xpath=".//span[contains(text(),'Mode')]/following-sibling::*|.//div[contains(@class,'mode')]")
        duration = get_text_safe(card, css=".duration", xpath=".//span[contains(text(),'Duration')]/following-sibling::*|.//div[contains(@class,'duration')]")
        fees = get_text_safe(card, css=".fees, .fee", xpath=".//span[contains(text(),'Fee') or contains(text(),'Fees')]/following-sibling::*")
        apply_by = get_text_safe(card, css=".apply-by, .apply_by", xpath=".//span[contains(text(),'Apply') or contains(text(),'apply')]/following-sibling::*")

        if not (title or company):
            continue

        item = {
            "Title": title,
            "Company": company,
            "Location": location,
            "Mode": mode,
            "Duration": duration,
            "Fees": fees,
            "Apply-by": apply_by,
        }

        if keyword:
            kw = keyword.lower()
            if not (kw in (item["Title"] or "").lower() or kw in (item["Company"] or "").lower()):
                continue

        results.append(item)

    return results


def click_next_page(driver) -> bool:
    next_selectors = [
        (By.CSS_SELECTOR, "a[rel='next']"),
        (By.LINK_TEXT, "Next"),
        (By.PARTIAL_LINK_TEXT, "Next"),
        (By.CSS_SELECTOR, "button[aria-label='Next']"),
        (By.CSS_SELECTOR, "li.next a"),
        (By.XPATH, "//a[contains(., 'Next') or contains(., 'next')]")
    ]

    for by, sel in next_selectors:
        try:
            elems = driver.find_elements(by, sel)
            if not elems:
                continue
            for el in elems:
                try:
                    cls = el.get_attribute("class") or ""
                    aria_disabled = el.get_attribute("aria-disabled")
                    disabled = el.get_attribute("disabled")
                    if aria_disabled and aria_disabled.lower() == "true":
                        continue
                    if disabled:
                        continue
                    if "disabled" in cls.lower():
                        continue
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    WebDriverWait(driver, 8).until(EC.staleness_of(el))
                    return True
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
        except Exception:
            continue

    try:
        pagination = driver.find_elements(By.CSS_SELECTOR, "ul.pagination li a, nav[role='navigation'] a")
        for el in pagination:
            text = (el.text or "").strip().lower()
            if "next" in text:
                try:
                    el.click()
                    WebDriverWait(driver, 8).until(EC.staleness_of(el))
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    return False


def scrape_site(start_url: str, headless: bool = True, max_pages: Optional[int] = None, keyword: Optional[str] = None) -> List[Dict[str, str]]:
    driver = create_driver(headless=headless)
    try:
        logging.info("Opening %s", start_url)
        driver.get(start_url)

        all_results: List[Dict[str, str]] = []
        page_num = 0

        while True:
            page_num += 1
            logging.info("Scraping page %d", page_num)

            wait_for_visible(driver, By.TAG_NAME, "body", timeout=8)

            page_results = scrape_cards_on_page(driver, keyword=keyword)
            logging.info("Scraped %d items from page %d", len(page_results), page_num)
            all_results.extend(page_results)

            if max_pages and page_num >= max_pages:
                logging.info("Reached max pages limit (%d)", max_pages)
                break

            has_next = click_next_page(driver)
            if not has_next:
                logging.info("No next page found; ending pagination")
                break

            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(0.5)

        return all_results
    finally:
        driver.quit()


def save_results(rows: List[Dict[str, str]], csv_path: str = "vtu_internships.csv", json_path: Optional[str] = None):
    if not rows:
        logging.info("No rows to save")
        return

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    logging.info("Saved %d records to %s", len(df), csv_path)
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        logging.info("Saved JSON to %s", json_path)


def parse_args():
    parser = argparse.ArgumentParser(description="VTU InternYet internships scraper")
    parser.add_argument("--url", type=str, required=False, default="https://vtuinternyet.in/browse-internships", help="Start URL for internship listings")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to scrape (default: all)")
    parser.add_argument("--keyword", type=str, default=None, help="Optional keyword filter for Title or Company")
    parser.add_argument("--json", type=str, default=None, help="Optional path to save JSON output")
    parser.add_argument("--output", type=str, default="vtu_internships.csv", help="CSV output filename")
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_args()

    logging.info("Starting scraper")
    rows = scrape_site(start_url=args.url, headless=args.headless, max_pages=args.max_pages, keyword=args.keyword)

    save_results(rows, csv_path=args.output, json_path=args.json)
    logging.info("Scraping complete. Total items: %d", len(rows))


if __name__ == "__main__":
    main()
