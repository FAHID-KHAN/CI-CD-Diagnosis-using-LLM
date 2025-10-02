# rag_system.py - Retrieval-Augmented Generation for CI/CD Diagnosis

import json
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import requests
from bs4 import BeautifulSoup
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import re

@dataclass
class DocumentChunk:
    """Represents a chunk of documentation"""
    chunk_id: str
    source: str
    title: str
    content: str
    url: str
    section: str
    embedding: Optional[np.ndarray] = None

@dataclass
class RetrievalResult:
    """Result from document retrieval"""
    chunks: List[DocumentChunk]
    relevance_scores: List[float]
    query: str

class DocumentationScraper:
    """Scrape and process documentation from official sources"""
    
    DOCUMENTATION_SOURCES = {
        'npm': 'https://docs.npmjs.com',
        'maven': 'https://maven.apache.org/guides/',
        'pip': 'https://pip.pypa.io/en/stable/',
        'docker': 'https://docs.docker.com',
        'github_actions': 'https://docs.github.com/en/actions',
        'gradle': 'https://docs.gradle.org',
        'pytest': 'https://docs.pytest.org',
        'jest': 'https://jestjs.io/docs'
    }
    
    def __init__(self, cache_dir: str = "./doc_cache"):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CI-CD-Diagnostic-Research/1.0'
        })
    
    def scrape_documentation(self, source: str, max_pages: int = 100) -> List[Dict]:
        """Scrape documentation from a source"""
        if source not in self.DOCUMENTATION_SOURCES:
            raise ValueError(f"Unknown source: {source}")
        
        base_url = self.DOCUMENTATION_SOURCES[source]
        pages = []
        
        print(f"Scraping {source} documentation from {base_url}")
        
        # Start with the main page
        pages_to_visit = [base_url]
        visited = set()
        
        while pages_to_visit and len(pages) < max_pages:
            url = pages_to_visit.pop(0)
            
            if url in visited:
                continue
            
            visited.add(url)
            
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Extract main content
                    content = self._extract_content(soup, source)
                    if content:
                        pages.append({
                            'source': source,
                            'url': url,
                            'title': soup.find('title').text if soup.find('title') else url,
                            'content': content
                        })
                    
                    # Find links to other documentation pages
                    links = self._extract_doc_links(soup, base_url, url)
                    pages_to_visit.extend(links)
                
            except Exception as e:
                print(f"Error scraping {url}: {e}")
                continue
        
        print(f"Scraped {len(pages)} pages from {source}")
        return pages
    
    def _extract_content(self, soup: BeautifulSoup, source: str) -> str:
        """Extract main content from HTML"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Try common content selectors
        content_selectors = [
            'main', 'article', '.content', '#content',
            '.documentation', '.doc-content'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                return content_elem.get_text(separator='\n', strip=True)
        
        # Fallback to body
        body = soup.find('body')
        return body.get_text(separator='\n', strip=True) if body else ""
    
    def _extract_doc_links(self, soup: BeautifulSoup, base_url: str, current_url: str) -> List[str]:
        """Extract links to other documentation pages"""
        links = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                href = base_url.rstrip('/') + href
            elif not href.startswith('http'):
                href = current_url.rsplit('/', 1)[0] + '/' + href
            
            # Only include documentation links
            if base_url in href and href not in links:
                links.append(href)
        
        return links

class DocumentChunker:
    """Split documents into smaller chunks for retrieval"""
    
    @staticmethod
    def chunk_by_section(document: Dict, max_chunk_size: int = 500) -> List[DocumentChunk]:
        """Split document into chunks by section"""
        content = document['content']
        
        # Try to split by headers
        sections = re.split(r'\n(?=[A-Z][^\n]{0,100}\n)', content)
        
        chunks = []
        chunk_id = 0
        
        for section in sections:
            # Extract section title
            lines = section.split('\n', 1)
            title = lines[0] if lines else "Untitled"
            section_content = lines[1] if len(lines) > 1 else section
            
            # Further split if too large
            if len(section_content) > max_chunk_size:
                # Split by paragraphs
                paragraphs = section_content.split('\n\n')
                current_chunk = []
                current_size = 0
                
                for para in paragraphs:
                    if current_size + len(para) > max_chunk_size and current_chunk:
                        # Create chunk
                        chunks.append(DocumentChunk(
                            chunk_id=f"{document['source']}_{chunk_id}",
                            source=document['source'],
                            title=title,
                            content='\n\n'.join(current_chunk),
                            url=document['url'],
                            section=title
                        ))
                        chunk_id += 1
                        current_chunk = [para]
                        current_size = len(para)
                    else:
                        current_chunk.append(para)
                        current_size += len(para)
                
                # Add remaining
                if current_chunk:
                    chunks.append(DocumentChunk(
                        chunk_id=f"{document['source']}_{chunk_id}",
                        source=document['source'],
                        title=title,
                        content='\n\n'.join(current_chunk),
                        url=document['url'],
                        section=title
                    ))
                    chunk_id += 1
            else:
                chunks.append(DocumentChunk(
                    chunk_id=f"{document['source']}_{chunk_id}",
                    source=document['source'],
                    title=title,
                    content=section_content,
                    url=document['url'],
                    section=title
                ))
                chunk_id += 1
        
        return chunks

class VectorStore:
    """Vector database for document retrieval"""
    
    def __init__(self, collection_name: str = "cicd_docs", persist_directory: str = "./chroma_db"):
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # Initialize embedding model
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "CI/CD documentation chunks"}
        )
    
    def add_documents(self, chunks: List[DocumentChunk]):
        """Add document chunks to vector store"""
        print(f"Adding {len(chunks)} chunks to vector store...")
        
        # Generate embeddings
        texts = [chunk.content for chunk in chunks]
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        
        # Prepare data for insertion
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = [
            {
                'source': chunk.source,
                'title': chunk.title,
                'url': chunk.url,
                'section': chunk.section
            }
            for chunk in chunks
        ]
        
        # Add to collection in batches
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_end = min(i + batch_size, len(chunks))
            self.collection.add(
                ids=ids[i:batch_end],
                embeddings=embeddings[i:batch_end].tolist(),
                documents=texts[i:batch_end],
                metadatas=metadatas[i:batch_end]
            )
        
        print(f"Successfully added {len(chunks)} chunks")
    
    def search(self, query: str, n_results: int = 5, 
              source_filter: Optional[str] = None) -> RetrievalResult:
        """Search for relevant documentation"""
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])[0]
        
        # Prepare where clause for filtering
        where_clause = {"source": source_filter} if source_filter else None
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where_clause
        )
        
        # Parse results
        chunks = []
        scores = []
        
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                chunks.append(DocumentChunk(
                    chunk_id=results['ids'][0][i],
                    source=results['metadatas'][0][i]['source'],
                    title=results['metadatas'][0][i]['title'],
                    content=results['documents'][0][i],
                    url=results['metadatas'][0][i]['url'],
                    section=results['metadatas'][0][i]['section']
                ))
                scores.append(results['distances'][0][i] if 'distances' in results else 1.0)
        
        return RetrievalResult(
            chunks=chunks,
            relevance_scores=scores,
            query=query
        )

class RAGEnhancedDiagnoser:
    """Diagnostic system enhanced with RAG"""
    
    def __init__(self, vector_store: VectorStore, llm_diagnoser):
        self.vector_store = vector_store
        self.llm_diagnoser = llm_diagnoser
    
    def extract_tool_context(self, log_content: str) -> List[str]:
        """Extract which tools/technologies are mentioned in the log"""
        tools = []
        
        tool_patterns = {
            'npm': r'\bnpm\b',
            'maven': r'\bmaven\b|\bpom\.xml\b',
            'pip': r'\bpip\b|\brequirements\.txt\b',
            'docker': r'\bdocker\b|\bDockerfile\b',
            'gradle': r'\bgradle\b|\bbuild\.gradle\b',
            'pytest': r'\bpytest\b',
            'jest': r'\bjest\b',
            'github_actions': r'github actions|\bworkflow\b'
        }
        
        for tool, pattern in tool_patterns.items():
            if re.search(pattern, log_content, re.IGNORECASE):
                tools.append(tool)
        
        return tools
    
    def create_rag_prompt(self, log_content: str, error_type: str, 
                         retrieved_docs: RetrievalResult) -> str:
        """Create prompt with retrieved documentation"""
        doc_context = "\n\n".join([
            f"[Documentation from {chunk.source} - {chunk.section}]\n{chunk.content}\nSource: {chunk.url}"
            for chunk in retrieved_docs.chunks
        ])
        
        return f"""You are an expert DevOps engineer analyzing CI/CD pipeline failures.
You have access to official documentation that may help provide more accurate fixes.

RETRIEVED DOCUMENTATION:
{doc_context}

BUILD LOG:
{log_content}

INSTRUCTIONS:
1. Analyze the build log to identify the root cause
2. Use the retrieved documentation to provide accurate, official guidance
3. When suggesting fixes, cite specific documentation sections
4. Provide exact commands or configuration changes based on official docs
5. Include the documentation URL for each recommendation

Respond in JSON format:
{{
    "error_type": "{error_type}",
    "failure_lines": [line numbers],
    "root_cause": "Clear explanation",
    "suggested_fix": "Actionable fix with documentation references",
    "documentation_references": [
        {{"source": "tool_name", "url": "doc_url", "relevance": "why this is relevant"}}
    ],
    "confidence_score": 0.0-1.0,
    "grounded_evidence": [
        {{"line_number": X, "content": "exact line", "is_error": true}}
    ],
    "reasoning": "Analysis steps"
}}"""
    
    async def diagnose_with_rag(self, log_content: str, temperature: float = 0.1) -> Dict:
        """Perform diagnosis with RAG enhancement"""
        # Step 1: Initial error detection
        tools_detected = self.extract_tool_context(log_content)
        
        # Step 2: Retrieve relevant documentation
        retrieval_results = []
        
        for tool in tools_detected:
            # Create search query based on error patterns
            search_query = f"{tool} error configuration troubleshooting"
            results = self.vector_store.search(search_query, n_results=3, source_filter=tool)
            retrieval_results.extend(results.chunks)
        
        # If no specific tools detected, do a general search
        if not retrieval_results:
            general_query = "build failure error troubleshooting"
            results = self.vector_store.search(general_query, n_results=5)
            retrieval_results = results.chunks
        
        # Step 3: Create enhanced prompt
        rag_prompt = self.create_rag_prompt(
            log_content,
            "unknown",
            RetrievalResult(chunks=retrieval_results[:5], relevance_scores=[], query="")
        )
        
        # Step 4: Get LLM diagnosis with documentation context
        diagnosis = await self.llm_diagnoser.diagnose(rag_prompt, temperature)
        
        return diagnosis

class DocumentationIndexBuilder:
    """Build and maintain the documentation index"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.scraper = DocumentationScraper()
        self.chunker = DocumentChunker()
    
    def build_index(self, sources: List[str], max_pages_per_source: int = 50):
        """Build the complete documentation index"""
        all_chunks = []
        
        for source in sources:
            print(f"\n=== Processing {source} ===")
            
            # Scrape documentation
            documents = self.scraper.scrape_documentation(source, max_pages=max_pages_per_source)
            
            # Chunk documents
            for doc in documents:
                chunks = self.chunker.chunk_by_section(doc)
                all_chunks.extend(chunks)
            
            print(f"Processed {len(documents)} documents into chunks")
        
        # Add all chunks to vector store
        print(f"\n=== Adding {len(all_chunks)} total chunks to vector store ===")
        self.vector_store.add_documents(all_chunks)
        
        print("\n=== Index building complete ===")
        return len(all_chunks)
    
    def update_index(self, source: str):
        """Update documentation for a specific source"""
        print(f"Updating index for {source}")
        
        # Scrape latest documentation
        documents = self.scraper.scrape_documentation(source)
        
        # Chunk and add
        all_chunks = []
        for doc in documents:
            chunks = self.chunker.chunk_by_section(doc)
            all_chunks.extend(chunks)
        
        self.vector_store.add_documents(all_chunks)
        print(f"Updated {len(all_chunks)} chunks for {source}")

class RAGEvaluator:
    """Evaluate RAG-enhanced diagnosis performance"""
    
    @staticmethod
    def evaluate_retrieval_quality(test_cases: List[Dict], vector_store: VectorStore) -> Dict:
        """Evaluate retrieval quality"""
        results = {
            'precision_at_k': [],
            'recall_at_k': [],
            'mrr': [],  # Mean Reciprocal Rank
            'ndcg': []  # Normalized Discounted Cumulative Gain
        }
        
        for test_case in test_cases:
            query = test_case['query']
            relevant_docs = set(test_case['relevant_doc_ids'])
            
            # Retrieve documents
            retrieval_result = vector_store.search(query, n_results=10)
            retrieved_ids = [chunk.chunk_id for chunk in retrieval_result.chunks]
            
            # Calculate metrics
            relevant_retrieved = [doc_id in relevant_docs for doc_id in retrieved_ids]
            
            # Precision@K and Recall@K
            k = 5
            precision_k = sum(relevant_retrieved[:k]) / k
            recall_k = sum(relevant_retrieved[:k]) / len(relevant_docs) if relevant_docs else 0
            
            results['precision_at_k'].append(precision_k)
            results['recall_at_k'].append(recall_k)
            
            # Mean Reciprocal Rank
            for i, is_relevant in enumerate(relevant_retrieved):
                if is_relevant:
                    results['mrr'].append(1 / (i + 1))
                    break
            else:
                results['mrr'].append(0)
        
        # Aggregate results
        return {
            'mean_precision_at_5': np.mean(results['precision_at_k']),
            'mean_recall_at_5': np.mean(results['recall_at_k']),
            'mean_reciprocal_rank': np.mean(results['mrr'])
        }
    
    @staticmethod
    def compare_with_without_rag(test_logs: List[Dict], 
                                 base_diagnoser, 
                                 rag_diagnoser) -> Dict:
        """Compare diagnosis with and without RAG"""
        base_results = []
        rag_results = []
        
        for log in test_logs:
            # Without RAG
            base_diagnosis = base_diagnoser.diagnose(log['log_content'])
            base_results.append({
                'log_id': log['log_id'],
                'fix_quality': log.get('fix_quality_base', 0),
                'has_documentation_reference': False
            })
            
            # With RAG
            rag_diagnosis = rag_diagnoser.diagnose_with_rag(log['log_content'])
            rag_results.append({
                'log_id': log['log_id'],
                'fix_quality': log.get('fix_quality_rag', 0),
                'has_documentation_reference': len(rag_diagnosis.get('documentation_references', [])) > 0
            })
        
        return {
            'base_avg_quality': np.mean([r['fix_quality'] for r in base_results]),
            'rag_avg_quality': np.mean([r['fix_quality'] for r in rag_results]),
            'docs_reference_rate': np.mean([r['has_documentation_reference'] for r in rag_results])
        }

# Example usage and utilities
class RAGSystem:
    """Complete RAG system orchestrator"""
    
    def __init__(self, persist_directory: str = "./rag_data"):
        self.vector_store = VectorStore(persist_directory=persist_directory)
        self.index_builder = DocumentationIndexBuilder(self.vector_store)
    
    def initialize(self, rebuild_index: bool = False):
        """Initialize the RAG system"""
        if rebuild_index:
            print("Building documentation index...")
            sources = ['npm', 'maven', 'pip', 'docker', 'github_actions', 'gradle', 'pytest', 'jest']
            self.index_builder.build_index(sources, max_pages_per_source=30)
        else:
            print("Using existing documentation index")
    
    def create_enhanced_diagnoser(self, llm_diagnoser):
        """Create RAG-enhanced diagnoser"""
        return RAGEnhancedDiagnoser(self.vector_store, llm_diagnoser)
    
    def search_documentation(self, query: str, tool: Optional[str] = None, 
                           n_results: int = 5) -> List[Dict]:
        """Search documentation manually"""
        results = self.vector_store.search(query, n_results=n_results, source_filter=tool)
        
        return [
            {
                'source': chunk.source,
                'title': chunk.title,
                'section': chunk.section,
                'content': chunk.content,
                'url': chunk.url,
                'relevance_score': score
            }
            for chunk, score in zip(results.chunks, results.relevance_scores)
        ]
    
    def get_statistics(self) -> Dict:
        """Get system statistics"""
        try:
            collection_count = self.vector_store.collection.count()
            
            return {
                'total_chunks': collection_count,
                'status': 'operational',
                'sources': list(DocumentationScraper.DOCUMENTATION_SOURCES.keys())
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

# Example usage
if __name__ == "__main__":
    # Initialize RAG system
    rag_system = RAGSystem(persist_directory="./cicd_docs_db")
    
    # Build index (first time only)
    rag_system.initialize(rebuild_index=False)
    
    # Search for documentation
    results = rag_system.search_documentation(
        query="npm install dependency error resolution",
        tool="npm",
        n_results=5
    )
    
    print("Search Results:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']} ({result['source']})")
        print(f"   Section: {result['section']}")
        print(f"   URL: {result['url']}")
        print(f"   Content preview: {result['content'][:200]}...")
    
    # Get statistics
    stats = rag_system.get_statistics()
    print(f"\nSystem Statistics: {json.dumps(stats, indent=2)}")