from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from openai import OpenAI
import google.generativeai as genai
import cohere
import json
import os
from dotenv import load_dotenv
from duckduckgo_search import DDGS
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

app = Flask(__name__)
CORS(app)

load_dotenv()
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
cohere_client = cohere.Client(api_key=os.getenv('COHERE_API_KEY'))
ASSISTANT_ID = "asst_v2se6YGN5d3xm4voj2k8eMOb"

# Create a thread pool executor
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        domain = data.get("domain")
        
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        
        if domain in ['newtab', 'chrome://newtab', 'about:blank'] or domain.startswith(('chrome://', 'about:', 'edge://')):
            return jsonify({
                "status": "error",
                "message": "Cannot analyze browser-specific pages",
                "domain": domain
            }), 400
        
        if not domain.startswith(('http://', 'https://')):
            domain = 'http://' + domain
        print("Gemini ke bhi pehle: ", domain)
        legal_urls = get_legal_urls(domain)
        print(legal_urls)
        
        if not legal_urls["privacy_policy"] and not legal_urls["terms_and_conditions"]:
            return jsonify({
                "status": "error",
                "message": "Legal documents not found",
                "domain": domain
            }), 404
        

        futures = []
        if legal_urls["privacy_policy"]:
            futures.append(executor.submit(policy_check, legal_urls["privacy_policy"]))
        if legal_urls["terms_and_conditions"]:
            futures.append(executor.submit(policy_check, legal_urls["terms_and_conditions"]))
        
        try:
            results = [future.result(timeout=30) for future in futures]
            print(results)
        except concurrent.futures.TimeoutError:
            return jsonify({
                "status": "error",
                "message": "Policy analysis timed out",
                "domain": domain
            }), 504
        
        is_safe = all(result[0] == "Policy Safe!" for result in results)
        print(is_safe)
        
        response_data = {
            "status": "success",
            "domain": domain,
            "privacy_policy": legal_urls["privacy_policy"],
            "terms_and_conditions": legal_urls["terms_and_conditions"],
            "is_direct": legal_urls["direct"],
            "is_safe": is_safe,
            "policy_analysis": results
        }
        urls_future = executor.submit(set_scale, results )
        response_data["trust_score"] = urls_future.result(timeout=30)
        print("Trust score:", response_data["trust_score"])
        
        if not is_safe:
            company_name = domain.split('//')[-1].split('.')[0]
            if company_name in ['www', 'app', 'web']:
                company_name = domain.split('//')[-1].split('.')[1]
                
            related_future = executor.submit(get_related_websites, company_name)
            
            try:
                related_sites = related_future.result(timeout=30)
                print("Related sites:", related_sites)
                urls_future = executor.submit(get_official_urls, related_sites)
                official_urls = urls_future.result(timeout=30)
                print("Official URLs:", official_urls)
                response_data["alternatives"] = official_urls
                print("Alternatives:", response_data["alternatives"])
            except concurrent.futures.TimeoutError:
                response_data["alternatives"] = {"error": "Retrieving alternatives timed out"}

        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def get_official_urls(company_names):
    urls = {}

    with DDGS() as ddgs:
        for company in company_names:
            query = (f"{company} official site")
            search_results = ddgs.text(query, max_results=1)

            if search_results:
                urls[company] = search_results[0]["href"]

            else:
                urls[company] = "URL not found"

    return urls


def set_scale(lst):
    
    prompt = (f"The following list contains problems in a website's privacy policy: {lst[0]}. "
          f"Based on these issues, assign a trust score from 1 to 10. "
          f"A higher number means the website is more trustworthy, while a lower number "
          f"means it's less trustworthy."
            f"if {lst[0]} is policy safe then give a score of 10. "
              f"Else decrease the score based on the problems."
          f"Return only a single integer between 1 and 10, nothing else."
        f"Do nor return any text just a single integer")



    response = cohere_client.generate(
        model = "command",
        prompt = prompt,
        max_tokens = 2,
        temperature = 0.0,
        k = 0,
        stop_sequences = ["\n"]
    )

    ai_response = response.generations[0].text.strip()

    try:
        score = int(ai_response)
        if 1 <= score <= 10:
            return score

    except ValueError:
        pass

    return -1


def get_related_websites(company_name: str) -> list:
    # start logging time
    import time
    time_start = time.time()
    print("Time start:", time_start)
    prompt = (f"Provide a list of exactly three websites or apps that are similar to {company_name}."  
            f' Rules: '
              f'- Only return the names of the websites or apps. '
              f'- No explanations, descriptions, or extra words.  '
              f'- The response must contain exactly three names.'
              f'- Do not include unrelated websites.  ')

    response = cohere_client.generate(
        model="command",
        prompt=prompt,
        max_tokens=50,
        temperature=0.7
    )
    curr_time = time.time()
    print("Time taken:", curr_time - time_start)
    suggestions = response.generations[0].text.strip().split("\n")

    lst = []
    for s in suggestions:
        if s:
            lst.append(s)

        if len(lst) == 3:
            break
    curr_time = time.time()
    print("Time taken:", curr_time - time_start)
    print("Related sites func:", lst)
    return lst

def extract_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract headings and paragraphs
        texts = []
        for tag in soup.find_all(["h1", "h2", "h3", "p"]):
            text = tag.get_text(strip=True)
            if text:  # Only add non-empty text
                texts.append(text)

        if not texts:
            return "No readable text found in the privacy policy."
            
        return "\n".join(texts)  # Combine into a readable format
    except Exception as e:
        print(f"Error extracting text: {e}")
        return "Error extracting text from the policy page."


def policy_check(url):
    try:
        lst = []
        text = extract_text(url)
        
        # Check if text is empty or too short
        if not text or text == "Error extracting text from the policy page." or len(text) < 10:
            return ["Privacy Concerns Detected", "Could not extract meaningful text from the privacy policy."]
        
        # Limit text length to avoid token limits
        if len(text) > 8000:
            text = text[:8000]
            
        thread = openai_client.beta.threads.create()

        # Send the URL as a message to the assistant
        openai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=text
        )

        # Run the assistant on the thread
        run = openai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Wait for the assistant to respond
        while run.status not in ["completed", "failed"]:
            run = openai_client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        if run.status == "failed":
            return ["Analysis failed", "Could not analyze the policy"]
            
        # Retrieve the assistant's response
        messages = openai_client.beta.threads.messages.list(thread_id=thread.id)
        assistant_response = messages.data[0].content[0].text.value

        lst.append(assistant_response)

        if assistant_response == "Policy Safe!":
            return lst
       
        # Send the URL as a message to the assistant
        openai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Elaborate with quote"
        )

        # Run the assistant on the thread
        run = openai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Wait for the assistant to respond
        while run.status not in ["completed", "failed"]:
            run = openai_client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        if run.status == "failed":
            lst.append("Could not elaborate on the analysis")
            return lst

        # Retrieve the assistant's response
        messages = openai_client.beta.threads.messages.list(thread_id=thread.id)
        assistant_response = messages.data[0].content[0].text.value

        lst.append(assistant_response)

        return lst
    except Exception as e:
        print(f"Error in policy check: {e}")
        return ["Error analyzing policy", str(e)]



def get_legal_urls(website_url):
    prompt = f"""
Provide the terms and conditions and privacy policy URLs for the given domain name: {website_url}.

Your response must adhere to the following strict guidelines to prevent errors and ensure accuracy:

1. **Domain Verification**: Confirm that the provided domain name is a valid, publicly accessible website.

2. **Direct vs. Indirect:**
   - If the terms and conditions and privacy policy are found directly on the given domain, provide those URLs. Set the `"direct"` key in the JSON response to `true`.
   - If the given domain redirects to or is a subsidiary of a parent company (e.g., a product page on a company's main website), locate the terms and conditions and privacy policy on the parent company's site. Provide those URLs and set the `"direct"` key in the JSON response to `false`.
   - If you find that the domain is owned by a parent company, mention the **parent company** in the response.

3. **URL Accuracy**: Verify that the URLs provided are valid and lead directly to the terms and conditions and privacy policy pages.

4. **Error Handling**:
   - If the terms and conditions or privacy policy cannot be found, set the corresponding key's value to `false`.
   - If you found that the site doesn't has any terms and conditions or privacy policy, set the corresponding key's value to `false` without any kind of explanation.
   - If the domain is invalid or does not exist, return:
     ```json
     {{
       "terms_and_conditions": false,
       "privacy_policy": false,
       "direct": false
     }}
     ```

5. **Strict JSON Format**: The response MUST be in the following format:
   ```json
   {{
     "terms_and_conditions": "<URL or false>",
     "privacy_policy": "<URL or false>",
     "direct": <true or false>
   }}
    ```
6. **Do not include any additional information or text in the response.**
   - STRICTLY DO NOT GIVE ANY EXPLANATION OR DESCRIPTION.
   - ALL RESPONSES MUST BE IN THE STRICT JSON FORMAT.
   - DO NOT INCLUDE ANY ADDITIONAL TEXT OR COMMENTS.
   - PROVIDE ONLY THE REQUESTED INFORMATION.
"""
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    
    model = genai.GenerativeModel(model_name="gemini-2.0-flash")
    response = model.generate_content(prompt)
    print("Response from sohel : ", response)
    json_text = response.text.replace("```json", "").replace("```", "").strip()
    print("Json text : ", json_text)
    return json.loads(json_text)
    

# Returns a list of 3 values
def extract_important_html(url) -> str:
    try:
        important_elements = []

        options = Options()
        options.add_argument("--headless")  # Headless mode
        options.add_argument("--disable-gpu")  # Prevents GPU-related issues
        options.add_argument("--no-sandbox")  # Helps in restricted environments
        options.add_argument("--window-size=1920,1080")  # Ensures full page loading
        
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        driver.implicitly_wait(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        for hidden in soup.find_all(style=lambda v: v and ("display:none" in v.lower() or "opacity:0" in v.lower())):
            important_elements.append(str(hidden))

        for tag in soup.find_all(["a", "form", "script", "meta"]):
            content = str(tag)
            if len(content) > 500: 
                continue
            important_elements.append(content)

        return "\n".join(important_elements) 
    
    except Exception as e:
        return f"Error: {e}"
    


    

def security_check(url: str):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    ASSISTANT_ID = "asst_vZcbERUnnB1DGgz7ase0EZig"
    lst = []
    text = extract_important_html(url)
    thread = client.beta.threads.create()

    text = text[0: 60000]

   
    
    # Send the URL as a message to the assistant
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=text
    )

    # Run the assistant on the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    # Wait for the assistant to respond
    while run.status != "completed":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )



    # Retrieve the assistant's response
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_response = messages.data[0].content[0].text.value
   
   

    lst.append(assistant_response)

    if assistant_response == "Security Safe!":
        lst.append("")
        lst.append("Safe")
        return lst
   
    # Send the URL as a message to the assistant
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Elaborate"
    )

    # Run the assistant on the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    # Wait for the assistant to respond
    while run.status != "completed":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )

    # Retrieve the assistant's response
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_response = messages.data[0].content[0].text.value

    lst.append(assistant_response)

    # Send the URL as a message to the assistant
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="How is the safety"
    )

    # Run the assistant on the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    # Wait for the assistant to respond
    while run.status != "completed":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )

    # Retrieve the assistant's response
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_response = messages.data[0].content[0].text.value

    lst.append(assistant_response)

    return lst
    

@app.route("/")
def index():
    return jsonify({"status": "API is running", "endpoints": ["/analyze"]})


@app.route("/test")
def test():
    lst = security_check("https://openai.com")
    return jsonify(lst)


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
