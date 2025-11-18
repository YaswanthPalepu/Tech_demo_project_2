# Environment Variables Guide

## Your Setup

**Embeddings:** Ollama (qwen3-embedding:latest)
**LLM:** OpenAI GPT-4o-mini

This guide documents all environment variables - **NO hardcoded values!**

---

## 🔧 Required Environment Variables

### For Ollama Embeddings

```bash
# Ollama server address
export OLLAMA_HOST=http://172.190.86.69:11434

# Embedding model (used by the codebase indexer)
export OLLAMA_EMBED_MODEL=qwen3-embedding:latest

# Vector dimension for embeddings
export VECTOR_DIM=1024

# (Optional) LLM model - not used by embeddings, just for reference
export OLLAMA_MODEL=deepseek-r1:latest
```

### For OpenAI LLM (GPT-4o-mini)

```bash
# OpenAI API endpoint (Azure OpenAI)
export AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/

# OpenAI API key
export AZURE_OPENAI_API_KEY=your-api-key-here

# Deployment name (your GPT-4o-mini deployment)
export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini

# (Optional) API version
export AZURE_OPENAI_API_VERSION=2023-12-01-preview
```

### For Auto-Fixer Behavior

```bash
# Enable embeddings (default: true)
export USE_EMBEDDINGS=true

# Enable verbose output for debugging
export AUTOFIXER_VERBOSE=true

# (Optional) LLM temperature - some Azure deployments don't support this
# export AUTOFIXER_LLM_TEMPERATURE=0.7
```

---

## 📋 Complete Setup Script

Save this as `setup_env.sh`:

```bash
#!/bin/bash

# ============================================================================
# Environment Variables for Auto-Test-Fixer with Ollama Embeddings
# ============================================================================

# --- Ollama Embeddings ---
export OLLAMA_HOST=http://172.190.86.69:11434
export OLLAMA_EMBED_MODEL=qwen3-embedding:latest
export VECTOR_DIM=1024
export OLLAMA_MODEL=deepseek-r1:latest  # For reference only

# --- OpenAI LLM (GPT-4o-mini) ---
export AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
export AZURE_OPENAI_API_KEY=your-api-key-here
export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
export AZURE_OPENAI_API_VERSION=2023-12-01-preview

# --- Auto-Fixer Settings ---
export USE_EMBEDDINGS=true
export AUTOFIXER_VERBOSE=true

# Verify settings
echo "✓ Environment variables set:"
echo "  Ollama Host: $OLLAMA_HOST"
echo "  Embedding Model: $OLLAMA_EMBED_MODEL"
echo "  Vector Dim: $VECTOR_DIM"
echo "  OpenAI Deployment: $AZURE_OPENAI_DEPLOYMENT"
echo "  Embeddings Enabled: $USE_EMBEDDINGS"
```

**Usage:**
```bash
# Source the script to set variables in current shell
source setup_env.sh

# Or use with command
source setup_env.sh && python run_auto_fixer.py ...
```

---

## 🔍 How Variables Are Used

### Embedding System (Ollama)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `OLLAMA_HOST` | `ollama_client.py` | Ollama server URL |
| `OLLAMA_EMBED_MODEL` | `codebase_indexer.py` | Model for generating embeddings |
| `VECTOR_DIM` | `codebase_indexer.py` | Dimension of embedding vectors |

**Code Path:**
```
run_auto_fixer.py
  → AutoTestFixerOrchestrator
    → EmbeddingContextExtractor
      → CodebaseIndexer
        → ollama_client.py (loads from env)
```

### LLM System (OpenAI)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `AZURE_OPENAI_ENDPOINT` | `openai_client.py` | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | `openai_client.py` | API authentication |
| `AZURE_OPENAI_DEPLOYMENT` | `llm_classifier.py`, `llm_fixer.py` | GPT model deployment |

**Code Path:**
```
run_auto_fixer.py
  → AutoTestFixerOrchestrator
    → LLMClassifier
      → openai_client.py (loads from env)
```

---

## ✅ Verification

### Test Ollama Connection

```bash
python -c "
import os
os.environ['OLLAMA_HOST'] = 'http://172.190.86.69:11434'
os.environ['OLLAMA_EMBED_MODEL'] = 'qwen3-embedding:latest'
os.environ['VECTOR_DIM'] = '1024'

import sys
sys.path.insert(0, 'src')

# Test
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('ollama_client', Path('src/gen/ollama_client.py'))
ollama = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ollama)

result = ollama.test_ollama_connection()
print('✅ Success!' if result else '❌ Failed')
"
```

### Test OpenAI Connection

```bash
python -c "
import os
os.environ['AZURE_OPENAI_ENDPOINT'] = 'your-endpoint'
os.environ['AZURE_OPENAI_API_KEY'] = 'your-key'
os.environ['AZURE_OPENAI_DEPLOYMENT'] = 'gpt-4o-mini'

import sys
sys.path.insert(0, 'src')

# Test
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('openai_client', Path('src/gen/openai_client.py'))
openai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(openai)

result = openai.validate_client_configuration()
print('✅ Success!' if result else '❌ Failed')
"
```

### Run Full Test

```bash
cd /home/user/Tech_demo_project_2
source setup_env.sh  # Your env vars
python test_ollama_embeddings.py
```

---

## 🔄 Variable Priority

The system checks variables in this order:

### Embedding Model
1. Constructor parameter (if provided)
2. `OLLAMA_EMBED_MODEL` env var
3. `OPENAI_EMBEDDING_MODEL` env var
4. Fallback: `qwen3-embedding:latest`

### Vector Dimension
1. `VECTOR_DIM` env var (highest priority) ✓
2. Infer from model name (`small` → 1536, `large` → 3072)
3. Fallback: 1024

### Embedding Client
1. If `OLLAMA_HOST` or `OLLAMA_EMBED_MODEL` set → Use Ollama
2. Otherwise → Use OpenAI
3. If both fail → Set to None (graceful degradation)

---

## 🐛 Troubleshooting

### Issue: "No embedding client available"

**Check:**
```bash
echo $OLLAMA_HOST
echo $OLLAMA_EMBED_MODEL
```

**Fix:** Set the variables and restart

### Issue: "Wrong vector dimension"

**Check:**
```bash
echo $VECTOR_DIM
```

**Fix:** Set to `1024` for qwen3-embedding

### Issue: "LLM API error"

**Check:**
```bash
echo $AZURE_OPENAI_ENDPOINT
echo $AZURE_OPENAI_DEPLOYMENT
```

**Fix:** Verify OpenAI credentials are correct

### Issue: "403 Forbidden from Ollama"

**Not a configuration issue!** This is from your Ollama server.

**Check server:**
```bash
curl $OLLAMA_HOST/api/tags
```

---

## 📝 Best Practices

### 1. Use a `.env` file

Create `.env` in project root:
```bash
# .env
OLLAMA_HOST=http://172.190.86.69:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:latest
VECTOR_DIM=1024

AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
```

Load with:
```bash
export $(cat .env | xargs)
```

### 2. Never commit credentials

Add to `.gitignore`:
```
.env
setup_env.sh  # If it contains secrets
*.key
```

### 3. Verify before running

```bash
# Quick check
env | grep -E "OLLAMA|AZURE_OPENAI" | sort

# Should show all your variables
```

### 4. Separate environments

```bash
# Development
export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini

# Production
export AZURE_OPENAI_DEPLOYMENT=gpt-4
```

---

## 🎯 Summary

**Your configuration uses:**
- ✅ `OLLAMA_HOST` - Ollama server address
- ✅ `OLLAMA_EMBED_MODEL` - qwen3-embedding:latest
- ✅ `VECTOR_DIM` - 1024
- ✅ `AZURE_OPENAI_ENDPOINT` - Your OpenAI endpoint
- ✅ `AZURE_OPENAI_API_KEY` - Your API key
- ✅ `AZURE_OPENAI_DEPLOYMENT` - gpt-4o-mini

**NO hardcoded values!** Everything is configurable via environment variables.

**Separation of concerns:**
- **Embeddings:** Ollama (local, free, private)
- **LLM:** OpenAI (cloud, paid, powerful)

This gives you the best of both worlds! 🚀
