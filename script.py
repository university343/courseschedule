from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import tempfile
import shutil

# Import ChromeDriverManager from webdriver_manager
from webdriver_manager.chrome import ChromeDriverManager

# Create a temporary directory for Chrome's user data
tmp_user_data_dir = tempfile.mkdtemp()

options = Options()
# Using the new headless mode as recommended by Selenium
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument(f"--user-data-dir={tmp_user_data_dir}")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

def take_screenshot(label):
    filename = f"{label}_{int(time.time())}.png"
    try:
        driver.save_screenshot(filename)
        print(f"Screenshot saved as {filename}")
    except Exception as e:
        print(f"Failed to take screenshot: {e}")

try:
    # Sanity check: navigate to selenium.dev to verify driver functionality
    print("Navigating to http://selenium.dev for sanity check...")
    driver.get("http://selenium.dev")
    time.sleep(3)  # Wait a few seconds to ensure the page loads
    take_screenshot("selenium_dev")
    
    # Now navigate to the target URL
    url = "https://ttb.utoronto.ca/"  # Replace with the correct starting URL if needed
    print(f"Navigating to target URL: {url}")
    driver.get(url)
    take_screenshot("target_page_initial")
    
    # Wait for course elements to load
    print("Waiting for course elements to load...")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
    )
    print("Course elements found.")
    
    # Initialize a list to store course data from all pages
    all_course_data = []

    # Loop through pages
    while True:
        print("Expanding accordion buttons on current page...")
        # Click all accordion buttons to expand course details
        accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
        for idx, button in enumerate(accordion_buttons):
            try:
                print(f"Clicking accordion button {idx+1}/{len(accordion_buttons)}")
                WebDriverWait(driver, 10).until(lambda d: button.is_enabled() and button.is_displayed())
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                button.click()
                time.sleep(1)  # Allow time for content to expand
            except Exception as e:
                print(f"Error clicking accordion button {idx+1}: {e}")
                take_screenshot(f"accordion_button_error_{idx+1}")

        # Parse the current page content
        html = driver.page_source
        take_screenshot("page_after_expanding")
        soup = BeautifulSoup(html, "html.parser")
        courses = soup.select("app-course")
        course_data = []

        print(f"Found {len(courses)} course elements.")
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

            course_data.append({
                "code_title": code_title,
                "campus": campus,
                "session": session,
                "notes": notes,
                "sections": sections
            })

        all_course_data.extend(course_data)

        # Check if a next page is available
        print("Looking for 'Next' page link...")
        next_page_links = driver.find_elements(
            By.XPATH, "//a[contains(@class, 'page-link') and text()='Next' and not(ancestor::li[contains(@class, 'disabled')])]"
        )
        if not next_page_links:
            print("No 'Next' page link found. Ending pagination.")
            break
        else:
            print("Navigating to next page...")
            next_page_links[0].click()
            time.sleep(2)
            take_screenshot("next_page_loaded")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
            )

    # Save the collected data to a JSON file
    with open('course_data.json', 'w') as f:
        json.dump(all_course_data, f, indent=4)
    print("Scraping complete! Data saved to course_data.json")

except Exception as e:
    print(f"An error occurred: {e}")
    take_screenshot("error_occurred")
    
finally:
    driver.quit()
    shutil.rmtree(tmp_user_data_dir, ignore_errors=True)
    print("Driver closed and temporary user data directory cleaned up.")
