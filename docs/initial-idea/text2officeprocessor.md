Below is a **Windsurf-compatible Software Design Specification (SDS)**. It is structured so an autonomous coding system can directly implement it with minimal ambiguity.

---

# SOFTWARE SPECIFICATION

## Project: Text2OfficeProcessor Intelligent Converter

---

# 1. OBJECTIVE

Build a production-grade system that converts:

- **Input**: `.md`, `.txt`, `.html`

- **Output**:
  
  - `.pptx`
  
  - `.docx`
  
  - `.xlsx`

Using:

- A **template-driven approach**

- **Programmatic rendering (primary)**

- **LLM-assisted normalization, mapping, and validation (secondary)**

Strict constraint:

> Layout generation MUST be deterministic and programmatic.  
> LLM MUST NOT generate final documents directly.

---

# 2. CORE PRINCIPLES

Derived from rule file :

### 2.1 Deterministic Rendering

- All final document construction:
  
  - PPTX → `python-pptx` (SlidePart cloning)
  
  - DOCX → `python-docx` (body injection)
  
  - XLSX → `openpyxl` (structured mapping)

- No LLM-based document generation

### 2.2 Template Preservation

- Never rebuild layouts

- Always:
  
  - Clone (PPTX)
  
  - Inject (DOCX)
  
  - Map (XLSX)

### 2.3 LLM Scope (STRICT)

Allowed:

- Markdown normalization

- Content structuring

- Slide/type mapping

- Rule-based validation

Forbidden:

- Generating PPTX/DOCX content directly

---

# 3. HIGH-LEVEL ARCHITECTURE

```
                ┌──────────────────────┐
                │      USER INPUT      │
                │ md/txt/html + tmpl  │
                └─────────┬────────────┘
                          │
              ┌───────────▼────────────┐
              │   INPUT PREPROCESSOR   │
              │ normalize + parse      │
              └───────────┬────────────┘
                          │
              ┌───────────▼────────────┐
              │   LLM NORMALIZATION    │
              │ structuring + tagging  │
              └───────────┬────────────┘
                          │
              ┌───────────▼────────────┐
              │   CONTENT PLANNER      │
              │ slide/map generator    │
              └───────────┬────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ PPTX ENGINE  │  │ DOCX ENGINE  │  │ XLSX ENGINE  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └──────────┬──────┴──────┬──────────┘
                  ▼             ▼
         ┌────────────────────────────┐
         │ VALIDATION PIPELINE        │
         │ programmatic + LLM         │
         └───────────┬────────────────┘
                     ▼
         ┌────────────────────────────┐
         │ FINAL OUTPUT FILES         │
         └────────────────────────────┘
```

---

# 4. MODULE DEFINITIONS

---

## 4.1 INPUT PREPROCESSOR

### Responsibilities

- Accept:
  
  - `.md`, `.txt`, `.html`

- Normalize:
  
  - encoding
  
  - whitespace
  
  - markdown artifacts

- Extract:
  
  - headings
  
  - paragraphs
  
  - lists
  
  - tables
  
  - images

### Output Schema

```json
{
  "document": {
    "sections": [
      {
        "title": "string",
        "content": [],
        "type": "paragraph | list | table | image"
      }
    ]
  }
}
```

---

## 4.2 LLM NORMALIZATION MODULE

### Purpose

Convert raw parsed content into **structured semantic format**

### Input

- Parsed document

- Rule file

### Output

```json
{
  "slides": [
    {
      "intent": "title | bullets | stats | diagram",
      "content": {
        "title": "...",
        "bullets": [],
        "body": "...",
        "visual_hint": "chart | flowchart | table"
      }
    }
  ]
}
```

### Constraints

- No formatting decisions

- No layout decisions

- Only semantic tagging

---

## 4.3 CONTENT PLANNER

### Responsibilities

Maps structured content to template-compatible schema

### Output (CRITICAL)

```markdown
## SLIDE 1 — template_index: 0
- placeholder: "Section Name Here" → "Intro"

---

## SLIDE 2 — template_index: 3
- placeholder: "Multi Point Slide" → "Key Ideas"
- bullets:
  - "Point 1"
  - "Point 2"
```

This format MUST match rule file exactly

---

## 4.4 PPTX ENGINE

### Implementation Requirements

Strictly follow:

- SlidePart cloning

- Run-level text replacement

- No layout mutation

### Key APIs

- `duplicate_slide()` (MANDATORY)

- `_normalize()` (text normalization)

- 3-layer replacement:
  
  - run-level
  
  - paragraph-level
  
  - cross-run

### Flow

```
Load Template
→ Clone Slide
→ Inject Content
→ Repeat
→ Remove Template Slides
```

### Diagram Handling

If `visual_hint == flowchart`:

- Generate Draw.io XML

- Convert XML → PNG

- Insert image

---

## 4.5 DOCX ENGINE

### Method

Template Injection (NOT Pandoc-first)

### Steps

1. Load template

2. Clear body (preserve images)

3. Copy content from structured DOCX

4. Maintain element order

5. Copy:
   
   - runs
   
   - paragraph styles
   
   - tables

### CRITICAL RULE

Preserve order via:

```python
for child in source.element.body:
```

(from rule file )

---

## 4.6 XLSX ENGINE

### Purpose

Convert structured content into:

- tables

- reports

- structured sheets

### Schema

```json
{
  "sheets": [
    {
      "name": "Sheet1",
      "columns": ["A", "B"],
      "rows": [
        ["val1", "val2"]
      ]
    }
  ]
}
```

### Implementation

- Use `openpyxl`

- Auto-detect:
  
  - tables
  
  - bullet lists → rows
  
  - sections → sheets

---

## 4.7 VALIDATION PIPELINE

### 4.7.1 Programmatic Checks

- Remove:
  
  - `**`, `__`, `---`

- Ensure:
  
  - no empty placeholders
  
  - images exist
  
  - structure valid

### 4.7.2 LLM Validation

Guided by rule file:

Checks:

- formatting correctness

- semantic coherence

- Visual appearance of slide to be maintained. No text going out of slide or un aligned etc.

- Tables and diagrams being in place.

- Table size, shape, content and type is to be proper (applies in docx aslo)

- Fontsize, type etc maintained.

- slide appropriateness

---

# 5. RULE FILE SYSTEM

### Purpose

Central authority for:

- formatting rules

- mapping logic

- validation rules

### Example

```yaml
pptx:
  title_max_length: 80
  bullets_max: 6

docx:
  preserve_headers: true

xlsx:
  max_columns: 20
```

---

# 6. LLM ABSTRACTION LAYER

### Requirement

Must support:

- Ollama

- OpenAI API

- Claude

- OpenRouter

- Groq

- Local models

### Interface

```python
class LLMProvider:
    def generate(self, prompt: str) -> str:
        pass
```

### Implementations

- `OllamaProvider`

- `OpenAIProvider`

- `ClaudeProvider`

- `OpenrouterProvider`

---

# 7. DRAW.IO INTEGRATION

### Flow

```
Structured Data
→ XML Generator
→ draw.io XML
→ PNG Export
→ Insert into PPTX/DOCX
```

### Output

```xml
<mxfile>
  <diagram>
    ...
  </diagram>
</mxfile>
```

---

# 8. PIPELINE FLOW

```
Input Files
→ Preprocess
→ LLM Normalize
→ Content Plan
→ Engine (PPTX/DOCX/XLSX)
→ Validation
→ Output
```

---

# 9. ERROR HANDLING

### Categories

| Type                | Action                 |
| ------------------- | ---------------------- |
| Template mismatch   | fail fast              |
| Missing placeholder | fallback mapping       |
| LLM failure         | retry / fallback rules |
| Rendering failure   | rollback               |
| Tables              |                        |

---

# 10. CONFIGURATION

### Example

```yaml
engine:
  pptx: true
  docx: true
  xlsx: true

llm:
  provider: ollama
  model: mistral

validation:
  strict: true
```

---

# 11. CLI INTERFACE

```bash
text2officeprocessor convert \
  --input input.md \
  --template template.pptx \
  --output output.pptx \
  --type pptx
```

---

# 12. DIRECTORY STRUCTURE

```
project/
├── core/
│   ├── parser/
│   ├── planner/
│   ├── engines/
│   ├── validation/
│   └── llm/
├── templates/
├── rules/
├── outputs/
└── cli/
```

---

# 13. NON-NEGOTIABLE RULES

From rule file :

1. No layout reconstruction

2. No markdown artifacts

3. No direct LLM document generation

4. Preserve template exactly

5. Always verify output visually/programmatically

---

# 14. EXTENSIONS

- Web UI

- Batch processing

- Template auto-learning

- Multi-language support

- Versioned templates

---

# 15. IMPLEMENTATION PRIORITY

### Phase 1

- PPTX engine (critical)

- Markdown parser

- Basic LLM normalization

### Phase 2

- DOCX engine

- Validation pipeline

### Phase 3

- XLSX engine

- Draw.io integration

---
