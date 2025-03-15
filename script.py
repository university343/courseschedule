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
import traceback  # Import the traceback module

# Import ChromeDriverManager from webdriver-manager
from webdriver_manager.chrome import ChromeDriverManager

# Configure Selenium for headless operation with extra options for GitHub Actions
options = Options()
options.add_argument("--headless=new")  # new headless mode, more stable
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--remote-debugging-port=9222")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

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
    # Find and click all accordion buttons to expand course details
        accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
        for button in accordion_buttons:
            try:
                # Ensure the button is clickable
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button))
                # Scroll to the button and click it
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                button.click()
                time.sleep(1)  # Brief pause to allow content to expand
            except Exception as e:
                print(f"Error clicking accordion button: {e}")
    
        # Get the current page source after expanding accordions
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
    
        # Extract course data from the current page
        courses = soup.select("app-course")
        course_data = []
        for course_elem in courses:
            # Extract course code and title
            header = course_elem.select_one(".accordion-button span")
            code_title = header.get_text(strip=True) if header else "N/A"
    
            # Extract course details
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
    
            # Extract section details
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
    
            # Store the course information
            course_data.append({
                "code_title": code_title,
                "campus": campus,
                "session": session,
                "notes": notes,
                "sections": sections
            })
    
        # Add the current page's course data to the overall list
        all_course_data.extend(course_data)
    
        # Check for the 'Next' page link and navigate if available
        next_page_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'page-link') and text()='Next' and not(ancestor::li[contains(@class, 'disabled')])]")
        if not next_page_links:
            # No 'Next' link or it's disabled, so exit the loop
            break
        else:
            # Click the 'Next' link to go to the next page
            next_page_link = next_page_links[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page_link)
            next_page_link.click()
            time.sleep(2)
            # Wait for the new page to load with course elements
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))

    # Save all collected data to a JSON file
    with open('course_data.json', 'w') as f:
        json.dump(all_course_data, f, indent=4)
    
        print("Scraping complete! Data saved to course_data.json")

except Exception as e:
    print(f"An error occurred: {e}")
    traceback.print_exc()  # Print the full traceback

finally:
    driver.quit()
    shutil.rmtree(tempfile.mkdtemp(), ignore_errors=True)
