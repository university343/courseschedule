import time
import json
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver 
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
import threading

# Global URL (change if needed)
URL = "https://ttb.utoronto.ca/"

# JavaScript to disable all animations and transitions
DISABLE_ANIMATIONS_JS = """
var css = document.createElement("style");
css.type = "text/css";
css.innerHTML = "* { animation: none !important; transition: none !important; }";
document.head.appendChild(css);
"""

# Create a lock to ensure that driver installation is not done concurrently
driver_install_lock = threading.Lock()

# Set a unique prefix for this scraping program.
# For example, for Summer Courses (Friday) you might use "summer_",
# for Next Year Fall-Winter (Saturday) use "next_fall_winter_",
# and for This Year Fall-Winter (Sunday) use "this_fall_winter_".
PREFIX = "next_fall_winter_"  # Change this accordingly.

def click_next(driver, num_clicks=1):
    """Click the 'Next' link num_clicks times.
       Returns False if a click fails (no more pages)."""
    for i in range(num_clicks):
        next_page_links = driver.find_elements(
            By.XPATH,
            "//a[contains(@class, 'page-link') and normalize-space()='Next' and not(ancestor::li[contains(@class, 'disabled')])]"
        )
        if not next_page_links:
            return False
        next_link = next_page_links[0]
        driver.execute_script("arguments[0].scrollIntoView(true);", next_link)
        next_link.click()
        time.sleep(2)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
        )
    return True

def process_pages(thread_index, total_threads=5):
    """
    Each thread:
      - Creates its own headless Chrome instance.
      - Loads the page, disables animations, selects all division options,
        and clicks the Search button.
      - Advances to its starting page based on thread_index.
      - Scrapes the current page (expanding accordions first),
        then clicks 'Next' and jumps ahead (total_threads pages per cycle).
    """
    options = Options()
    options.add_argument("--headless=new")  # new headless mode, more stable
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    from webdriver_manager.chrome import ChromeDriverManager
    with driver_install_lock:
        driver_path = ChromeDriverManager().install()
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    
    driver.get(URL)
    driver.execute_script(DISABLE_ANIMATIONS_JS)
    
    # Wait for division dropdown options and select them.
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "division"))
    )
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
        )
    )
    division_options = driver.find_elements(
        By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option"
    )
    print(f"Thread {thread_index}: Found division options:", len(division_options))
    for option in division_options:
        driver.execute_script("arguments[0].scrollIntoView(true);", option)
        driver.execute_script("arguments[0].click();", option)
        time.sleep(0.1)
    
    # Wait for session dropdown options and select them.
        WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.ID, "session"))
    )
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option")
        )
    )
    session_options = driver.find_elements(By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option")
    print("Found session options:", len(session_options))
    for option in session_options:
        driver.execute_script("arguments[0].scrollIntoView(true);", option)
        driver.execute_script("arguments[0].click();", option)
        time.sleep(0.5)
        
    # Click the Search button.
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Search']"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
    driver.execute_script("arguments[0].click();", search_button)
    
    # Check if the "No results found" message appears.
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.alert-info.results-error-info"))
        )
        print("No results found. Exiting search.")
        driver.quit()
        return []  # Exit immediately if no results.
    except Exception:
        # If the error message is not found within 5 seconds, continue.
        pass

    # Wait for course elements to load.
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
    )
    
    # Advance to the starting page based on thread_index.
    for i in range(thread_index):
        if not click_next(driver, 1):
            break
    
    thread_data = []
    while True:
        accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
        for button in accordion_buttons:
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button))
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                button.click()
                time.sleep(0.1)
            except Exception as e:
                print(f"Thread {thread_index}: Error clicking accordion button: {e}")
        
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
        thread_data.extend(page_data)
        
        next_page_links = driver.find_elements(
            By.XPATH,
            "//a[contains(@class, 'page-link') and normalize-space()='Next' and not(ancestor::li[contains(@class, 'disabled')])]"
        )
        if not next_page_links:
            break
        else:
            next_page_link = next_page_links[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page_link)
            next_page_link.click()
            time.sleep(0.5)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-course"))
            )
            if total_threads > 1:
                if not click_next(driver, total_threads - 1):
                    break
    
    driver.quit()
    return thread_data

def main():
    total_threads = 5
    all_course_data = []
    with ThreadPoolExecutor(max_workers=total_threads) as executor:
        futures = [executor.submit(process_pages, i, total_threads) for i in range(total_threads)]
        for future in futures:
            all_course_data.extend(future.result())
    
    # Save all collected data to a JSON file locally.
    with open('course_data.json', 'w') as f:
        json.dump(all_course_data, f, indent=4)
    
    print("Scraping complete! Data saved to course_data.json.")
    
    # Upload courses in chunks to Firestore, overwriting only documents from this program.
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        from firebase_admin.firestore import FieldPath
        # Initialize Firebase Admin with your service account key file
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        collection_ref = db.collection('courses')
        
        # Delete existing documents that were uploaded by this program.
        existing_docs = collection_ref.where(
            FieldPath.documentId(), '>=', PREFIX
        ).where(
            FieldPath.documentId(), '<', PREFIX + '\uf8ff'
        ).stream()
        for doc in existing_docs:
            doc.reference.delete()
        
        MAX_SIZE = 1048576  # 1 MiB in bytes
        chunk = []
        chunk_index = 1
        
        for course in all_course_data:
            temp_chunk = chunk + [course]
            temp_json = json.dumps(temp_chunk, indent=4)
            size_bytes = len(temp_json.encode('utf-8'))
            if size_bytes > MAX_SIZE:
                # Upload the current chunk before adding the current course.
                doc_id = f"{PREFIX}chunk_{chunk_index}"
                collection_ref.document(doc_id).set({'courses': chunk})
                chunk_index += 1
                chunk = [course]
            else:
                chunk = temp_chunk
        
        # Upload any remaining courses.
        if chunk:
            doc_id = f"{PREFIX}chunk_{chunk_index}"
            collection_ref.document(doc_id).set({'courses': chunk})
        
        print("Data uploaded to Firestore successfully in chunks!")
    except Exception as e:
        print("Failed to upload data to Firestore:", e)

if __name__ == "__main__":
    main()
