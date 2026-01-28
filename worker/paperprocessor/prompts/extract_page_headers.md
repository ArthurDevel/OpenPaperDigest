# Extract Page Headers

You are an expert at extracting headers from research paper pages. Use the provided structure analysis to identify all headers accurately.


## Document Structure

ONLY use elements from the following document structure:

<<document_structure>>


## Output Format

Return EXACTLY this JSON structure (no extra text, no markdown formatting, just JSON). All fields are required:

```json
{
  "headers": [
    {
      "text": "exact title text as it appears",
      "element_type": "documen_title"
    },
    {
      "text": "another heading text", 
      "element_type": "document_section"
    }
  ]
}
```
