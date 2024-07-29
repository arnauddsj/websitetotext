from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import datetime
import re

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Allow the Vue.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 10

def extract_metadata(content):
    # Simple extraction based on common patterns
    title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
    title = title_match.group(1) if title_match else ""
    
    description_match = re.search(r'<meta name="description" content="(.*?)"', content, re.IGNORECASE)
    description = description_match.group(1) if description_match else ""
    
    return {
        "title": title,
        "description": description,
        "keywords": [],  # We'd need more sophisticated parsing for keywords
        "author": "",
        "publishDate": "",
        "lastModified": "",
        "canonicalUrl": "",
        "robots": "",
        "ogTags": {}
    }

def parse_content(content):
    soup = BeautifulSoup(content, 'html.parser')
    parsed_content = []
    
    for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
        if element.name.startswith('h'):
            parsed_content.append({
                "type": "header",
                "level": int(element.name[1]),
                "text": element.get_text(strip=True)
            })
        elif element.name == 'p':
            parsed_content.append({
                "type": "paragraph",
                "text": element.get_text(strip=True)
            })
    
    return parsed_content

def extract_global_components(content):
    soup = BeautifulSoup(content, 'html.parser')
    
    header = {
        "logo": "",
        "navigation": []
    }
    
    nav = soup.find('nav')
    if nav:
        for link in nav.find_all('a'):
            header["navigation"].append({
                "text": link.get_text(strip=True),
                "url": link.get('href', '')
            })
    
    footer = {
        "copyright": "",
        "socialLinks": []
    }
    
    footer_elem = soup.find('footer')
    if footer_elem:
        copyright = footer_elem.find(string=re.compile(r'©|Copyright'))
        if copyright:
            footer["copyright"] = copyright.strip()
    
    return {"header": header, "footer": footer}

def transform_result(raw_result, base_url):
    transformed = {
        "website": {
            "domain": urlparse(base_url).netloc,
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "language": "en",
            "pages": [],
            "globalComponents": {}
        }
    }
    
    for url, content in raw_result.items():
        metadata = extract_metadata(content)
        parsed_content = parse_content(content)
        
        page = {
            "url": url,
            "type": "home" if url == base_url else "content",
            "metadata": metadata,
            "content": parsed_content
        }
        
        transformed["website"]["pages"].append(page)
        
        # Extract global components from the first page
        if not transformed["website"]["globalComponents"]:
            transformed["website"]["globalComponents"] = extract_global_components(content)
    
    return transformed

@app.post("/crawl")
async def crawl(request: CrawlRequest):
    # This is where you'd implement your actual crawling logic
    # For now, we'll use a dummy result
    dummy_result = {
        "result": {
            "https://example.com": "Example content for the home page",
            "https://example.com/about": "About page content",
            "https://example.com/contact": "Contact page content"
        }
    }
    
    transformed_result = transform_result(dummy_result["result"], request.url)
    return transformed_result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)