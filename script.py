from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
from threading import Thread
from urllib.parse import urlparse, parse_qs, urlencode

# Configure Selenium in headless mode
options = Options()
options.headless = True

# Disable CSS animations and transitions
disable_animations = """
var css = document.createElement("style");
css.type = "text/css";
css.innerHTML = "* { animation: none !important; transition: none !important; }";
document.head.appendChild(css);
"""

# Worker function to process a list of page URLs
def worker(urls, data_list):
    driver = webdriver.Chrome(options=options)
    driver.execute_script(disable_animations)
    for url in urls:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))
        
        # Find and click all accordion buttons to expand course details
        accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
        for button in accordion_buttons:
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button))
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                button.click()
                time.sleep(0.5)
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
        
        data_list.extend(course_data)
    
    driver.quit()

# Main thread setup
driver = webdriver.Chrome(options=options)
url = "https://ttb.utoronto.ca/"  # Replace with the correct starting URL
driver.get(url)
driver.execute_script(disable_animations)

# Wait for the division dropdown to be present
WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "division")))
# Wait until the custom checkbox options are present in the dropdown
WebDriverWait(driver, 10).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option"))
)
# Locate all division options and click each one
division_options = driver.find_elements(By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
print("Found division options:", len(division_options))
for option in division_options:
    driver.execute_script("arguments[0].scrollIntoView(true);", option)
    driver.execute_script("arguments[0].click();", option)
    time.sleep(0.1)

"""
WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "session")))
WebDriverWait(driver, 10).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option"))
)
session_options = driver.find_elements(By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option")
print("Found session options:", len(session_options))
for option in session_options:
    driver.execute_script("arguments[0].scrollIntoView(true);", option)
    driver.execute_script("arguments[0].click();", option)
    time.sleep(0.5)
"""

# Click "Search"
search_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Search']"))
)
driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
driver.execute_script("arguments[0].click();", search_button)

# Wait for course elements
WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))

# Determine total number of pages (example placeholder)
# In practice, replace with actual logic, e.g., parsing pagination info
# For now, assume we find it from page links or text like "Page 1 of 10"
try:
    page_links = driver.find_elements(By.CSS_SELECTOR, "a.page-link")
    page_numbers = [int(link.text) for link in page_links if link.text.isdigit()]
    total_pages = max(page_numbers) if page_numbers else 1
except:
    total_pages = 10  # Fallback if detection fails

# Get base URL after search
base_url = driver.current_url
parsed_url = urlparse(base_url)
query_params = parse_qs(parsed_url.query)

# Generate all page URLs
all_page_urls = []
for i in range(1, total_pages + 1):
    query_params['page'] = [str(i)]
    new_query = urlencode(query_params, doseq=True)
    new_url = parsed_url._replace(query=new_query).geturl()
    all_page_urls.append(new_url)

driver.quit()

# Initialize 5 threads
num_threads = 5
threads = []
thread_data = [[] for _ in range(num_threads)]

# Distribute pages (thread 0: 1,6,11; thread 1: 2,7,12; etc.)
for i in range(num_threads):
    thread_urls = all_page_urls[i::num_threads]
    t = Thread(target=worker, args=(thread_urls, thread_data[i]))
    threads.append(t)
    t.start()

# Wait for all threads to finish
for t in threads:
    t.join()

# Combine all course data
all_course_data = []
for data in thread_data:
    all_course_data.extend(data)

# Save all collected data to a JSON file
with open('course_data.json', 'w') as f:
    json.dump(all_course_data, f, indent=4)
