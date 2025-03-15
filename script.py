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

# Configure Selenium for headless operation with extra options for GitHub Actions
tmp_user_data_dir = tempfile.mkdtemp()

options = Options()
options.add_argument("--headless=new")  # new headless mode, more stable
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument(f"--user-data-dir={tmp_user_data_dir}")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--remote-debugging-port=9222")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get('http://selenium.dev')

try:
    # Load the initial page (adjust the URL if needed)
    url = "https://ttb.utoronto.ca/"  # Replace with the correct starting URL
    driver.get(url)

    # Wait for course elements to load
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
    )

    # Initialize a list to store course data from all pages
    all_course_data = []

    # Loop through pages
    while True:
        # Click all accordion buttons to expand course details
        accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
        for button in accordion_buttons:
            try:
                # Wait until the button is clickable
                WebDriverWait(driver, 10).until(lambda d: button.is_enabled() and button.is_displayed())
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                button.click()
                time.sleep(1)  # Allow time for content to expand
            except Exception as e:
                print(f"Error clicking accordion button: {e}")

        # Parse the current page content
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        courses = soup.select("app-course")
        course_data = []

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

        # Add the current page's data to the overall list
        all_course_data.extend(course_data)

        # Navigate to next page if available
        next_page_links = driver.find_elements(
            By.XPATH, "//a[contains(@class, 'page-link') and text()='Next' and not(ancestor::li[contains(@class, 'disabled')])]"
        )
        if not next_page_links:
            break
        else:
            next_page_links[0].click()
            time.sleep(2)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
            )

    # Save the collected data to a JSON file
    with open('course_data.json', 'w') as f:
        json.dump(all_course_data, f, indent=4)

    print("Scraping complete! Data saved to course_data.json")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    driver.quit()
    shutil.rmtree(tmp_user_data_dir, ignore_errors=True)
