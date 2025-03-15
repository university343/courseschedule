import time
import json
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import traceback
import tempfile
import shutil

from webdriver_manager.chrome import ChromeDriverManager

# Global URL
URL = "https://ttb.utoronto.ca/"

def disable_animations(driver):
    # Inject CSS to disable animations and transitions
    script = """
    var css = document.createElement("style");
    css.type = "text/css";
    css.innerHTML = "* { animation: none !important; transition: none !important; }";
    document.head.appendChild(css);
    """
    driver.execute_script(script)

def initialize_driver():
    options = Options()
    options.add_argument("--headless=new")  # new headless mode, more stable
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=9222")

def select_division_options(driver):
    # Wait for and click the division dropdown
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "division"))
    )
    division_dropdown = driver.find_element(By.ID, "division")
    driver.execute_script("arguments[0].click();", division_dropdown)
    
    # Wait for the custom division options to be present
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
        )
    )
    division_options = driver.find_elements(By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
    print("Found division options:", len(division_options))
    
    # Click each option (using JS click for custom elements)
    for option in division_options:
        driver.execute_script("arguments[0].scrollIntoView(true);", option)
        driver.execute_script("arguments[0].click();", option)
        time.sleep(0.1)

def click_search(driver):
    # Wait for and click the "Search" button
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Search']"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
    driver.execute_script("arguments[0].click();", search_button)
    time.sleep(2)  # Allow time for the search results to load

def scrape_current_page(driver):
    # Wait for course elements to load
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))
    
    # Expand all accordion buttons so that course details are visible
    accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
    for button in accordion_buttons:
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button))
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            button.click()
            time.sleep(0.5)
        except Exception as e:
            print(f"Error clicking accordion button: {e}")
    
    # Use BeautifulSoup to extract course data
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    courses = soup.select("app-course")
    page_data = []
    
    for course_elem in courses:
        header = course_elem.select_one(".accordion-button span")
        code_title = header.get_text(strip=True) if header else "N/A"
        
        body = course_elem.select_one(".accordion-body")
        if not body:
            campus = session = notes = "N/A"
        else:
            campus_elem = body.select_one("label:contains('Campus') + span")
            campus = campus_elem.get_text(strip=True) if campus_elem else "N/A"
            
            session_elem = body.select_one("label:contains('Session') + span")
            session = session_elem.get_text(strip=True) if session_elem else "N/A"
            
            notes_elem = body.select_one(".notes-details .notes")
            notes = notes_elem.get_text(strip=True) if notes_elem else "N/A"
        
        sections = []
        section_elems = course_elem.select(".course-sections app-course-section")
        for section_elem in section_elems:
            section_code_elem = section_elem.select_one(".header span")
            section_code = section_code_elem.get_text(strip=True) if section_code_elem else "N/A"
            details = section_elem.select(".section-item")
            section_info = {"code": section_code}
            
            for detail in details:
                label_elem = detail.select_one("label")
                label = label_elem.get_text(strip=True) if label_elem else ""
                value_elem = detail.select_one(".item-value")
                value = value_elem.get_text(strip=True) if value_elem else "N/A"
                
                if "Day/Time" in label:
                    section_info["day_time"] = value
                elif "Location" in label:
                    section_info["location"] = value
                elif "Instructor" in label:
                    section_info["instructor"] = value
                elif "Availability" in label:
                    section_info["availability"] = value
                elif "Waitlist" in label:
                    section_info["waitlist"] = value
                elif "Enrolment Controls" in label:
                    section_info["enrollment_control"] = value
                elif "Delivery Mode" in label:
                    section_info["delivery_mode"] = value
            sections.append(section_info)
        
        page_data.append({
            "code_title": code_title,
            "campus": campus,
            "session": session,
            "notes": notes,
            "sections": sections
        })
    return page_data

def click_next(driver, clicks=1):
    """Clicks the 'Next' link a specified number of times.
       Returns False if unable to click (i.e. end of pages)."""
    for _ in range(clicks):
        try:
            next_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//a[contains(@class, 'page-link') and normalize-space()='Next' and not(ancestor::li[contains(@class, 'disabled')])]"
                ))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_link)
            driver.execute_script("arguments[0].click();", next_link)
            time.sleep(0.2)  # Wait for the next page to load
        except Exception as e:
            print("No more pages or error clicking next:", e)
            return False
    return True

def process_pages(thread_index, total_threads=5):
    """
    Each thread uses its own Selenium driver to:
      1. Load the page, disable animations, select divisions, and click Search.
      2. Advance to a starting page based on thread_index (0 -> page 1, 1 -> page 2, etc.).
      3. Scrape the current page and then jump ahead total_threads pages.
    """
    initialize_driver()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=Options)
    collected_data = []
    try:
        select_division_options(driver)
        click_search(driver)
        
        # Advance to the starting page for this thread
        for _ in range(thread_index):
            if not click_next(driver, clicks=1):
                break
        
        # Loop through pages assigned to this thread
        while True:
            print(f"Thread {thread_index} processing page")
            page_data = scrape_current_page(driver)
            collected_data.extend(page_data)
            # Jump ahead by clicking 'Next' total_threads times
            if not click_next(driver, clicks=total_threads):
                break
    except Exception as e:
        print(f"Error in thread {thread_index}: {e}")
    finally:
        driver.quit()
    return collected_data

def main():
    all_course_data = []
    total_threads = 5
    # Use ThreadPoolExecutor to run 5 threads in parallel
    with ThreadPoolExecutor(max_workers=total_threads) as executor:
        futures = [executor.submit(process_pages, i, total_threads) for i in range(total_threads)]
        for future in futures:
            all_course_data.extend(future.result())
    
    # Save the collected data to a JSON file
    with open('course_data.json', 'w') as f:
        json.dump(all_course_data, f, indent=4)
    
    print("Scraping complete! Data saved to course_data.json.")

if __name__ == "__main__":
    main()
