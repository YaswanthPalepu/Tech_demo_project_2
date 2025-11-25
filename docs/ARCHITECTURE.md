# Architecture Workflow Diagram

## System Overview

This is an **AI-Powered Test Generation System** that analyzes Python projects, detects manual tests, and generates intelligent test coverage using AI.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Target Repository"
        TR[Python Project<br/>Flask/FastAPI/Django]
    end

    subgraph "Pipeline 1: Manual Test Detection & Execution"
        P1_MTD[Manual Test Detector<br/>detect_manual_tests.py]
        P1_PYTEST[pytest + coverage]
        P1_COV[Coverage Reports<br/>coverage.xml, htmlcov/]
        P1_SONAR[SonarQube Quality Gate]
    end

    subgraph "Pipeline 2: AI Test Generation"
        P2_ANALYZER[Code Analyzer<br/>analyzer.py]
        P2_FRAMEWORK[Framework Manager<br/>framework_handlers/]
        P2_GAP[Coverage Gap Analyzer<br/>coverage_gap_analyzer.py]
        P2_ORCHESTRATOR[Test Generation Orchestrator<br/>test_generation/orchestrator.py]
        P2_AI[AI Test Generator<br/>gen/enhanced_generate.py]
        P2_OPENAI[OpenAI/Azure OpenAI API]
        P2_WRITER[Test Writer<br/>gen/writer.py]
        P2_GIT[Git Commit & Push]
    end

    subgraph "Pipeline 3: AI Test Execution & Validation"
        P3_PYTEST[pytest + coverage]
        P3_COV[Coverage Reports]
        P3_SONAR[SonarQube Quality Gate]
        P3_DECISION[Deployment Decision]
    end

    TR --> P1_MTD
    P1_MTD --> P1_PYTEST
    P1_PYTEST --> P1_COV
    P1_COV --> P1_SONAR
    P1_COV --> P2_GAP

    TR --> P2_ANALYZER
    P2_ANALYZER --> P2_FRAMEWORK
    P2_FRAMEWORK --> P2_ORCHESTRATOR
    P2_GAP --> P2_ORCHESTRATOR
    P2_ORCHESTRATOR --> P2_AI
    P2_AI --> P2_OPENAI
    P2_OPENAI --> P2_AI
    P2_AI --> P2_WRITER
    P2_WRITER --> P2_GIT
    P2_GIT --> TR

    TR --> P3_PYTEST
    P3_PYTEST --> P3_COV
    P3_COV --> P3_SONAR
    P3_SONAR --> P3_DECISION

    style TR fill:#e1f5ff
    style P2_OPENAI fill:#fff4e1
    style P1_SONAR fill:#e8f5e9
    style P3_SONAR fill:#e8f5e9
    style P3_DECISION fill:#f3e5f5
```

## Detailed Component Architecture

```mermaid
graph TB
    subgraph "Entry Points"
        CLI[CLI Entry Point<br/>python -m src.gen]
        GHA[GitHub Actions Workflows]
        LOCAL[Local Pipeline Script<br/>local_pipeline-1.sh]
    end

    subgraph "Analysis Layer"
        ANALYZER[analyzer.py<br/>AST-based Code Analysis]
        MTD[detect_manual_tests.py<br/>Manual Test Detection]
        CGA[coverage_gap_analyzer.py<br/>Coverage Gap Analysis]
    end

    subgraph "Framework Detection Layer"
        FM[Framework Manager<br/>manager.py]
        FH_FASTAPI[FastAPI Handler]
        FH_FLASK[Flask Handler]
        FH_DJANGO[Django Handler]
        FH_UNIVERSAL[Universal Handler]
    end

    subgraph "Test Generation Core"
        ORCHESTRATOR[orchestrator.py<br/>Test Orchestration]
        GENERATOR[enhanced_generate.py<br/>Main Generator]
        GAP_GEN[gap_aware_analysis.py<br/>Gap-Focused Generation]
        PROMPT[enhanced_prompt.py<br/>Prompt Engineering]
        OPENAI[openai_client.py<br/>AI Integration]
    end

    subgraph "Post-Processing Layer"
        POSTPROCESS[postprocess.py<br/>Code Validation]
        WRITER[writer.py<br/>File Operations]
        IMPORT_RESOLVER[import_resolver.py<br/>Import Resolution]
        COV_OPTIMIZER[coverage_optimizer.py<br/>Coverage Optimization]
    end

    subgraph "Output & Integration"
        TEST_FILES[Generated Test Files<br/>tests/generated/]
        REPORTS[Coverage Reports<br/>coverage.xml]
        GIT[Git Operations<br/>Commit & Push]
        SONAR[SonarQube Integration]
    end

    CLI --> GENERATOR
    GHA --> GENERATOR
    LOCAL --> MTD

    GENERATOR --> ANALYZER
    GENERATOR --> FM
    MTD --> CGA
    CGA --> GAP_GEN

    ANALYZER --> ORCHESTRATOR
    FM --> FH_FASTAPI
    FM --> FH_FLASK
    FM --> FH_DJANGO
    FM --> FH_UNIVERSAL

    FH_FASTAPI --> ORCHESTRATOR
    FH_FLASK --> ORCHESTRATOR
    FH_DJANGO --> ORCHESTRATOR
    FH_UNIVERSAL --> ORCHESTRATOR

    ORCHESTRATOR --> GAP_GEN
    GAP_GEN --> GENERATOR
    GENERATOR --> PROMPT
    PROMPT --> OPENAI
    OPENAI --> POSTPROCESS

    POSTPROCESS --> WRITER
    WRITER --> IMPORT_RESOLVER
    IMPORT_RESOLVER --> COV_OPTIMIZER
    COV_OPTIMIZER --> TEST_FILES

    TEST_FILES --> GIT
    TEST_FILES --> REPORTS
    REPORTS --> SONAR

    style OPENAI fill:#fff4e1
    style SONAR fill:#e8f5e9
    style TEST_FILES fill:#e1f5ff
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Analyzer
    participant Framework
    participant Orchestrator
    participant AI
    participant Writer
    participant Git

    User->>CLI: python -m src.gen --target ./project
    CLI->>Analyzer: Analyze project structure
    Analyzer->>Analyzer: Parse AST, extract functions/classes
    Analyzer-->>CLI: Project analysis complete

    CLI->>Framework: Detect framework type
    Framework->>Framework: Check for FastAPI/Flask/Django
    Framework-->>CLI: Framework identified

    CLI->>Orchestrator: Start test generation
    Orchestrator->>Orchestrator: Check for coverage gaps
    Orchestrator->>AI: Generate tests with context

    loop For each uncovered component
        AI->>AI: Build prompt with code context
        AI->>External: Call OpenAI API
        External-->>AI: Generated test code
        AI->>Writer: Write test file
        Writer->>Writer: Validate & format code
        Writer-->>Orchestrator: Test file created
    end

    Orchestrator->>Git: Commit generated tests
    Git->>Git: git add, commit, push
    Git-->>User: Tests generated & pushed

    User->>CLI: Run pytest with coverage
    CLI->>CLI: Execute tests
    CLI-->>User: Coverage report
```

## Pipeline Flow Architecture

```mermaid
flowchart LR
    subgraph "Pipeline 1: Manual Test Analysis"
        P1_START[Start] --> P1_DETECT[Detect Manual Tests]
        P1_DETECT --> P1_RUN[Run Manual Tests]
        P1_RUN --> P1_COV[Generate Coverage]
        P1_COV --> P1_SONAR[Quality Gate Check]
        P1_SONAR --> P1_ARTIFACT[Upload Artifacts]
    end

    subgraph "Pipeline 2: AI Test Generation"
        P2_START[Start] --> P2_DOWNLOAD[Download Coverage]
        P2_DOWNLOAD --> P2_ANALYZE[Analyze Gaps]
        P2_ANALYZE --> P2_DETECT_FW[Detect Framework]
        P2_DETECT_FW --> P2_GEN[Generate AI Tests]
        P2_GEN --> P2_VALIDATE[Validate Tests]
        P2_VALIDATE --> P2_COMMIT[Commit & Push]
    end

    subgraph "Pipeline 3: AI Test Validation"
        P3_START[Start] --> P3_PULL[Pull Generated Tests]
        P3_PULL --> P3_RUN[Run AI Tests]
        P3_RUN --> P3_COV[Generate Coverage]
        P3_COV --> P3_SONAR[Quality Gate Check]
        P3_SONAR --> P3_DEPLOY{Pass?}
        P3_DEPLOY -->|Yes| P3_SUCCESS[Deploy Ready]
        P3_DEPLOY -->|No| P3_FAIL[Fix Required]
    end

    P1_ARTIFACT -.->|Triggers| P2_START
    P2_COMMIT -.->|Triggers| P3_START

    style P1_SONAR fill:#e8f5e9
    style P3_SONAR fill:#e8f5e9
    style P2_GEN fill:#fff4e1
    style P3_SUCCESS fill:#c8e6c9
    style P3_FAIL fill:#ffcdd2
```

## Coverage Gap Analysis Flow

```mermaid
flowchart TD
    START[Coverage Report Input] --> PARSE[Parse coverage.xml]
    PARSE --> HTMLCOV{htmlcov/ exists?}
    HTMLCOV -->|Yes| PARSE_HTML[Parse HTML Coverage]
    HTMLCOV -->|No| SKIP_HTML[Skip HTML parsing]

    PARSE_HTML --> MERGE[Merge Coverage Data]
    SKIP_HTML --> MERGE

    MERGE --> IDENTIFY[Identify Uncovered Lines]
    IDENTIFY --> MAP[Map to Functions/Classes]
    MAP --> PRIORITY[Prioritize by Impact]

    PRIORITY --> OUTPUT{Output Format}
    OUTPUT -->|JSON| JSON_FILE[coverage_gaps.json]
    OUTPUT -->|Report| TXT_FILE[gap_analysis.txt]

    JSON_FILE --> AI_GEN[Feed to AI Generator]
    TXT_FILE --> HUMAN_REVIEW[Human Review]

    AI_GEN --> TARGETED[Generate Targeted Tests]
    TARGETED --> VERIFY[Verify Coverage Increase]

    style START fill:#e1f5ff
    style AI_GEN fill:#fff4e1
    style TARGETED fill:#c8e6c9
    style VERIFY fill:#e8f5e9
```

## Framework Handler Architecture

```mermaid
graph TB
    subgraph "Framework Detection"
        INPUT[Project Analysis Input]
        MANAGER[Framework Manager]
        DETECT{Detect Framework}
    end

    subgraph "Framework Handlers"
        FASTAPI_H[FastAPI Handler<br/>- Route extraction<br/>- Dependency injection<br/>- Async support]
        FLASK_H[Flask Handler<br/>- Route extraction<br/>- Blueprint support<br/>- Context managers]
        DJANGO_H[Django Handler<br/>- View extraction<br/>- Model detection<br/>- URL patterns]
        UNIVERSAL_H[Universal Handler<br/>- Generic functions<br/>- Class methods<br/>- Module analysis]
    end

    subgraph "Test Templates"
        FASTAPI_T[FastAPI Test Templates<br/>- TestClient usage<br/>- Async fixtures]
        FLASK_T[Flask Test Templates<br/>- Test client setup<br/>- Context handling]
        DJANGO_T[Django Test Templates<br/>- TestCase classes<br/>- Database fixtures]
        UNIVERSAL_T[Universal Templates<br/>- pytest fixtures<br/>- Mock objects]
    end

    INPUT --> MANAGER
    MANAGER --> DETECT
    DETECT -->|FastAPI| FASTAPI_H
    DETECT -->|Flask| FLASK_H
    DETECT -->|Django| DJANGO_H
    DETECT -->|Unknown| UNIVERSAL_H

    FASTAPI_H --> FASTAPI_T
    FLASK_H --> FLASK_T
    DJANGO_H --> DJANGO_T
    UNIVERSAL_H --> UNIVERSAL_T

    FASTAPI_T --> OUTPUT[Test Generation]
    FLASK_T --> OUTPUT
    DJANGO_T --> OUTPUT
    UNIVERSAL_T --> OUTPUT

    style MANAGER fill:#e1f5ff
    style OUTPUT fill:#c8e6c9
```

## AI Test Generation Workflow

```mermaid
flowchart TD
    START[Start Generation] --> MODE{Generation Mode}

    MODE -->|Normal| FULL[Full Coverage Mode]
    MODE -->|Gap-Focused| GAP[Gap-Focused Mode]
    MODE -->|Maximum| MAX[Maximum Coverage Mode]

    FULL --> ANALYZE[Analyze All Code]
    GAP --> LOAD_GAPS[Load Coverage Gaps]
    MAX --> ANALYZE_DEEP[Deep Code Analysis]

    LOAD_GAPS --> FILTER[Filter Uncovered Code]
    ANALYZE --> EXTRACT[Extract All Components]
    ANALYZE_DEEP --> EXTRACT_DEEP[Extract All + Edge Cases]

    FILTER --> BUILD_PROMPT
    EXTRACT --> BUILD_PROMPT
    EXTRACT_DEEP --> BUILD_PROMPT

    BUILD_PROMPT[Build AI Prompt] --> CONTEXT[Add Code Context]
    CONTEXT --> FRAMEWORK_INFO[Add Framework Info]
    FRAMEWORK_INFO --> EXAMPLES[Add Test Examples]

    EXAMPLES --> CALL_AI[Call OpenAI API]
    CALL_AI --> RECEIVE[Receive Generated Code]

    RECEIVE --> VALIDATE{Valid Python?}
    VALIDATE -->|No| RETRY{Retry Count < 3?}
    RETRY -->|Yes| CALL_AI
    RETRY -->|No| LOG_ERROR[Log Error & Skip]

    VALIDATE -->|Yes| POSTPROCESS[Post-process Code]
    POSTPROCESS --> FORMAT[Format with Black]
    FORMAT --> ADD_IMPORTS[Add Missing Imports]
    ADD_IMPORTS --> WRITE_FILE[Write Test File]

    WRITE_FILE --> MORE{More Components?}
    MORE -->|Yes| BUILD_PROMPT
    MORE -->|No| COMPLETE[Generation Complete]

    LOG_ERROR --> MORE

    style CALL_AI fill:#fff4e1
    style VALIDATE fill:#e8f5e9
    style COMPLETE fill:#c8e6c9
    style LOG_ERROR fill:#ffcdd2
```

## Technology Stack

```mermaid
graph LR
    subgraph "Core Technologies"
        PYTHON[Python 3.9+]
        PYTEST[pytest]
        COVERAGE[coverage.py]
    end

    subgraph "AI/ML"
        OPENAI[OpenAI API]
        AZURE[Azure OpenAI]
        TREESITTER[tree-sitter-python]
    end

    subgraph "Web Frameworks"
        FASTAPI[FastAPI]
        FLASK[Flask]
        DJANGO[Django]
    end

    subgraph "CI/CD"
        GHA[GitHub Actions]
        SONAR[SonarQube]
        GIT[Git]
    end

    subgraph "Testing Tools"
        PYTEST_COV[pytest-cov]
        PYTEST_ASYNC[pytest-asyncio]
        PYTEST_MOCK[pytest-mock]
        HTTPX[httpx]
    end

    PYTHON --> PYTEST
    PYTHON --> COVERAGE
    PYTEST --> PYTEST_COV
    PYTEST --> PYTEST_ASYNC
    PYTEST --> PYTEST_MOCK

    OPENAI --> AZURE
    PYTHON --> TREESITTER

    GHA --> GIT
    GHA --> SONAR

    style PYTHON fill:#3776ab,color:#fff
    style OPENAI fill:#412991,color:#fff
    style GHA fill:#2088ff,color:#fff
```

## Key Features

### 1. Universal Project Support
- Works with any Python project structure
- Supports flat, nested, and package-based layouts
- Framework-agnostic with specialized handlers

### 2. Intelligent Gap Detection
- Analyzes coverage reports (XML + HTML)
- Identifies uncovered functions, classes, and methods
- Prioritizes test generation for maximum impact

### 3. Framework-Aware Generation
- Detects FastAPI, Flask, Django, or generic Python
- Uses framework-specific test patterns
- Handles async/sync, routes, views, and models

### 4. AI-Powered Generation
- Uses OpenAI/Azure OpenAI for intelligent test creation
- Context-aware prompts with code analysis
- Generates unit, integration, and E2E tests

### 5. Quality Assurance
- Validates generated code syntax
- Post-processes for import resolution
- Integrates with SonarQube for quality gates

### 6. CI/CD Integration
- Three-pipeline GitHub Actions workflow
- Automated test execution and validation
- Coverage tracking and reporting

## Usage Patterns

### Pattern 1: Full Generation
```bash
python -m src.gen --target ./my-project
```
Generates comprehensive test suite for entire project.

### Pattern 2: Gap-Focused Generation
```bash
export GAP_FOCUSED_MODE=1
python -m src.gen --target ./my-project
```
Generates tests only for uncovered code.

### Pattern 3: Pipeline Orchestration
```bash
./local_pipeline-1.sh
```
Runs complete workflow: detect → analyze → generate → test.

### Pattern 4: GitHub Actions
Push to repository triggers automated three-pipeline workflow.

## Configuration

### Environment Variables
- `TARGET_ROOT` - Target project directory
- `COVERAGE_MODE` - Coverage optimization mode
- `AZURE_OPENAI_ENDPOINT` - AI service endpoint
- `AZURE_OPENAI_API_KEY` - AI service API key
- `GAP_FOCUSED_MODE` - Enable gap-focused generation

### Configuration Files
- `pytest.ini` - Pytest configuration
- `requirements.txt` - Python dependencies
- `.github/workflows/*.yml` - CI/CD pipeline definitions

## Output Artifacts

### Generated Files
- `tests/generated/test_*.py` - AI-generated test files
- `coverage.xml` - Coverage report (Cobertura format)
- `htmlcov/` - HTML coverage report
- `coverage_gaps.json` - Gap analysis results
- `manual_test_result.json` - Manual test detection results

### Reports
- Coverage percentage and statistics
- Gap analysis with prioritization
- Test generation logs
- SonarQube quality metrics

---

**Version:** 1.0
**Last Updated:** 2025-11-25
**Project:** AI-Powered Test Generation System
