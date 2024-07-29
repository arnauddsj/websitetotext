from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import datetime
import re
from collections import Counter
from fastapi.responses import JSONResponse

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

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        normalized_url = url.rstrip('/')  # Remove trailing slash
        if normalized_url in visited:
            continue

        try:
            response = requests.get(url)
            response.encoding = 'utf-8'  # Explicitly set encoding to UTF-8
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results[normalized_url] = soup
                visited.add(normalized_url)

                # Find new links
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

@app.post("/crawl")
async def crawl(request: CrawlRequest):
    raw_result = crawl_website(request.url, request.max_pages)
    transformed_result = transform_result(raw_result, request.url)
    return JSONResponse(content=transformed_result, media_type="application/json; charset=utf-8")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)