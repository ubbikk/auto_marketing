# News Sources for AI/Automation Content

## Quick Recommendation

**For your project, start simple:** Use RSS feeds directly. They're free, don't require API keys, and you can filter with AI after fetching. Only move to paid APIs if you need sentiment analysis, full-text search, or massive scale.

---

## Option 1: RSS Feeds (Free, No API Key Needed)

### AI-Specific Feeds

| Source | RSS URL | Notes |
|--------|---------|-------|
| TechCrunch AI | `https://techcrunch.com/category/artificial-intelligence/feed/` | High quality, VC/startup angle |
| Ars Technica AI | `https://feeds.arstechnica.com/arstechnica/technology-lab` | Technical depth |
| The Verge | `https://www.theverge.com/rss/index.xml` | General tech, good for trends |
| Wired | `https://www.wired.com/feed/rss` | Longform, cultural angle |
| MIT Technology Review | `https://www.technologyreview.com/feed/` | Research-focused |
| VentureBeat AI | `https://venturebeat.com/category/ai/feed/` | Enterprise AI focus |
| The Guardian AI | `https://www.theguardian.com/technology/artificialintelligenceai/rss` | Mainstream perspective |
| IEEE Spectrum AI | `https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss` | Technical/engineering |

### Business/Automation Feeds

| Source | RSS URL | Notes |
|--------|---------|-------|
| TechCrunch Startups | `https://techcrunch.com/category/startups/feed/` | Startup news |
| Hacker News | `https://hnrss.org/frontpage` | Community-curated tech |
| Product Hunt | `https://www.producthunt.com/feed` | New products/tools |
| InfoQ | `https://feed.infoq.com/ai-ml-data-eng/` | Developer-focused |

### Research/Deep Dives

| Source | RSS URL | Notes |
|--------|---------|-------|
| OpenAI Blog | `https://openai.com/blog/rss.xml` | First-party announcements |
| Google AI Blog | `https://ai.googleblog.com/feeds/posts/default` | Research updates |
| Anthropic | `https://www.anthropic.com/feed.xml` | Claude/AI safety |
| DeepMind | `https://deepmind.google/blog/rss.xml` | Research papers |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` | Open source ML |

### Newsletters/Substacks (via RSS)

| Source | RSS URL | Notes |
|--------|---------|-------|
| The Rundown AI | `https://www.therundown.ai/feed` | Daily AI digest |
| Interconnects | `https://www.interconnects.ai/feed` | Technical analysis |
| One Useful Thing | `https://www.oneusefulthing.org/feed` | Ethan Mollick's practical AI |
| Simon Willison | `https://simonwillison.net/atom/everything/` | LLM tools/hacks |

---

## Option 2: News APIs (For More Control)

### Free Tier APIs

| API | Free Tier | Best For | Limitations |
|-----|-----------|----------|-------------|
| **NewsAPI.org** | 100 req/day | Quick prototype | 24hr delay on free, no commercial use |
| **NewsData.io** | 200 req/day | Commercial OK | Limited historical |
| **GNews** | 100 req/day | Simple queries | 10 articles/request |
| **World News API** | 500 req/day | Global coverage | Basic features only |
| **Webz.io Lite** | 1000 req/month | Archive access | 10 articles/call |
| **Currents API** | 600 req/day | Simple integration | Limited filtering |

### Worth Paying For (If You Scale)

| API | Starting Price | Why Pay |
|-----|----------------|---------|
| **NewsAPI.ai** | ~$50/mo | Semantic search, sentiment, entity extraction |
| **NewsCatcher** | ~$100/mo | Real-time, good filtering |
| **Perigon** | Custom | Full enrichment, AI tags |

---

## Option 3: Build Your Own Pipeline

### Simple Python RSS Fetcher

```python
import feedparser
from datetime import datetime, timedelta

AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://venturebeat.com/category/ai/feed/",
]

def fetch_recent_articles(feeds, hours=24):
    """Fetch articles from last N hours"""
    cutoff = datetime.now() - timedelta(hours=hours)
    articles = []
    
    for feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            # Parse published date
            published = datetime(*entry.published_parsed[:6])
            if published > cutoff:
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'summary': entry.get('summary', ''),
                    'published': published,
                    'source': feed.feed.title
                })
    
    return sorted(articles, key=lambda x: x['published'], reverse=True)

# Usage
articles = fetch_recent_articles(AI_FEEDS, hours=24)
for a in articles[:10]:
    print(f"[{a['source']}] {a['title']}")
```

### Filter with AI

```python
def is_relevant(article, topics=['AI', 'automation', 'LLM', 'chatbot']):
    """Use Claude/GPT to filter relevance"""
    prompt = f"""
    Is this article relevant to: {', '.join(topics)}?
    
    Title: {article['title']}
    Summary: {article['summary'][:500]}
    
    Respond only: YES or NO
    """
    # Call your LLM here
    # return response == "YES"
```

---

## Recommended Stack for Your Project

### Phase 1: MVP (Free)
1. Pick 5-6 RSS feeds from the AI/tech list above
2. Use `feedparser` to fetch daily
3. Filter with Claude to find relevant articles
4. Store in SQLite or JSON file

### Phase 2: Smarter Filtering
1. Add semantic search (embeddings) to find truly relevant news
2. Deduplicate similar stories across sources
3. Extract key entities/topics for content generation

### Phase 3: Scale (If Needed)
1. Move to NewsAPI.org or NewsData.io for broader coverage
2. Add sentiment analysis for opinion pieces
3. Cache aggressively to stay within rate limits

---

## Quick Start: Copy-Paste RSS List

```
# AI/ML News
https://techcrunch.com/category/artificial-intelligence/feed/
https://feeds.arstechnica.com/arstechnica/technology-lab
https://venturebeat.com/category/ai/feed/
https://www.wired.com/feed/category/business/topic/artificial-intelligence/latest/rss
https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss

# General Tech
https://www.theverge.com/rss/index.xml
https://feeds.arstechnica.com/arstechnica/index
https://www.wired.com/feed/rss

# Business/Startups  
https://techcrunch.com/category/startups/feed/
https://techcrunch.com/category/venture/feed/

# First-Party AI Companies
https://openai.com/blog/rss.xml
https://www.anthropic.com/feed.xml
https://ai.googleblog.com/feeds/posts/default

# Community
https://hnrss.org/frontpage
https://www.reddit.com/r/artificial/.rss
https://www.reddit.com/r/MachineLearning/.rss
```

---

## Notes

**RSS is underrated.** Most people jump to APIs, but RSS feeds are:
- Free forever
- No rate limits
- No API keys to manage
- Standardized format
- Often include full article text

**The AI filtering is the real work.** Whether you use RSS or APIs, you'll need to filter 100+ articles/day down to 3-5 worth posting about. That's where your AI pipeline adds value.

**Consider recency vs. relevance.** Breaking news (last 24h) is good for engagement but hard to add insight. Week-old analysis pieces give you more room to add perspective.
