from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import datetime
import re
from collections import Counter
from fastapi.responses import JSONResponse
import time
from dotenv import load_dotenv
import os
import logging

load_dotenv()

app = FastAPI()

# Update CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://websitetotext.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CrawlRequest(BaseModel):
    url: HttpUrl
    max_pages: int = 10

# Rate limiting
request_count = {}
RATE_LIMIT = 5  # requests
RATE_LIMIT_WINDOW = 60  # seconds

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    current_time = time.time()
    
    if client_ip in request_count:
        if current_time - request_count[client_ip]["timestamp"] > RATE_LIMIT_WINDOW:
            request_count[client_ip] = {"count": 1, "timestamp": current_time}
        else:
            request_count[client_ip]["count"] += 1
            if request_count[client_ip]["count"] > RATE_LIMIT:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
    else:
        request_count[client_ip] = {"count": 1, "timestamp": current_time}
    
    response = await call_next(request)
    return response

def extract_metadata(soup, url):
    metadata = {}

    # Extract title
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        metadata["title"] = title_tag.string.strip()

    # Extract meta tags
    for meta in soup.find_all('meta'):
        if 'name' in meta.attrs:
            name = meta.attrs['name'].lower()
            content = meta.attrs.get('content', '').strip()
            if content:
                if name in ['description', 'author']:
                    metadata[name] = content
                elif name == 'keywords':
                    metadata['keywords'] = [k.strip() for k in content.split(',') if k.strip()]
        elif 'property' in meta.attrs and meta.attrs['property'].startswith('og:'):
            og_name = meta.attrs['property'][3:]
            content = meta.attrs.get('content', '').strip()
            if content:
                if 'ogTags' not in metadata:
                    metadata['ogTags'] = {}
                metadata['ogTags'][og_name] = content

    # Extract canonical URL
    canonical = soup.find('link', rel='canonical')
    if canonical and 'href' in canonical.attrs:
        metadata['canonicalUrl'] = canonical.attrs['href']

    # Only include non-empty metadata fields
    return {k: v for k, v in metadata.items() if v}

def parse_content(soup):
    content = {
        "text": [],
        "images": [],
        "alts": [],
        "h1": [],
        "h2": [],
        "h3": [],
        "h4": [],
        "links": []
    }

    for element in soup.body.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div', 'img', 'a']):
        if element.name in ['h1', 'h2', 'h3', 'h4']:
            text = element.get_text(strip=True)
            if text:
                content[element.name].append(text)
        elif element.name in ['p', 'div']:
            # Extract text while preserving some structure
            texts = [t.strip() for t in element.stripped_strings]
            if texts:
                content["text"].extend(texts)
        elif element.name == 'img':
            src = element.get('src', '').strip()
            alt = element.get('alt', '').strip()
            if src:
                content["images"].append(src)
            if alt:
                content["alts"].append(alt)
        elif element.name == 'a':
            text = element.get_text(strip=True)
            href = element.get('href', '').strip()
            if text and href:
                content["links"].append({"text": text, "url": href})

    return content

def extract_repeated_content(soups):
    link_patterns = Counter()
    text_patterns = Counter()

    for soup in soups.values():
        page_links = set()
        page_texts = set()

        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a.get('href')
            if text and href:
                page_links.add((text, href))

        for p in soup.find_all(['p', 'span', 'div']):
            text = p.get_text(strip=True)
            if text:
                page_texts.add(text)

        link_patterns.update(page_links)
        text_patterns.update(page_texts)

    # Consider links that appear in at least 50% of pages as navigation
    num_pages = len(soups)
    navigation = [{"text": text, "url": url} for (text, url), count in link_patterns.items() if count >= num_pages * 0.5]

    # Consider text that appears in at least 80% of pages as footer content
    footer = [{"type": "text", "content": text} for text, count in text_patterns.items() if count >= num_pages * 0.8]

    return navigation, footer

def crawl_website(base_url, max_pages):
    visited = set()
    to_visit = [base_url]
    results = {}

    start_time = time.time()
    timeout = 30  # 30 seconds timeout

    while to_visit and len(visited) < max_pages:
        if time.time() - start_time > timeout:
            break

        url = to_visit.pop(0)
        normalized_url = url.rstrip('/')
        if normalized_url in visited:
            continue

        try:
            response = requests.get(url, timeout=5)  # 5 seconds timeout for each request
            response.encoding = 'utf-8'
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results[normalized_url] = soup
                visited.add(normalized_url)

                for link in soup.find_all('a', href=True):
                    new_url = urljoin(url, link['href'])
                    new_normalized_url = new_url.rstrip('/')
                    if new_normalized_url.startswith(base_url) and new_normalized_url not in visited:
                        to_visit.append(new_url)
        except Exception as e:
            print(f"Error crawling {url}: {e}")

    return results

def transform_result(raw_result, base_url):
    transformed = {
        "website": {
            "domain": urlparse(base_url).netloc,
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "language": "en",
            "pages": [],
        }
    }
    
    # Extract repeated content to identify navigation and footer
    navigation, footer = extract_repeated_content(raw_result)

    if navigation or footer:
        transformed["website"]["globalComponents"] = {}
        if navigation:
            transformed["website"]["globalComponents"]["navigation"] = navigation
        if footer:
            transformed["website"]["globalComponents"]["footer"] = footer

    for url, soup in raw_result.items():
        metadata = extract_metadata(soup, url)
        content = parse_content(soup)
        
        # Remove global components from page content
        content = {k: v for k, v in content.items() if v not in navigation and v not in footer}
        
        # Remove duplicates while preserving order
        for key in ['text', 'h1', 'h2', 'h3', 'h4']:
            content[key] = list(dict.fromkeys(content[key]))
        
        page = {
            "url": url.replace(base_url.rstrip('/'), ''),  # Normalize base_url as well
            "type": "home" if url == base_url.rstrip('/') else "content",
        }
        if metadata:
            page["metadata"] = metadata
        if content:
            page["content"] = content
        
        transformed["website"]["pages"].append(page)
    
    return transformed

@app.options("/crawl")
async def crawl_options():
    return JSONResponse(
        content={"message": "OK"},
        headers={
            "Access-Control-Allow-Origin": "https://websitetotext.com",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )

@app.post("/crawl")
async def crawl(request: CrawlRequest):
    logger.info(f"Received crawl request for URL: {request.url}")
    logger.info(f"Request body: {request.dict()}")
    try:
        result = await crawl_website(request.url, request.max_pages)
        logger.info(f"Crawl completed successfully. Result: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error during crawl: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5202)