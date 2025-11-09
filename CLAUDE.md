# TYPESCRIPT

## GUIDE: Coding Practices for Typescript

Format the code such that it is easy to read for a junior developer. Make sure to keep functionality the same, except if stated otherwise. Keep code simple, do not use fallbacks except if the user requests this, prefer raising errors in a simple way. Do not overcomplicate, simple is best.


## Coding Rules

- use JSDoc, including the params with a short explanation and what the function returns
- use interface for data transfer objects when data needs to be passed between classes. Where applicable, the result of a function should be an (updated) DTO.
- use dependency injection to inject instances of other classes that are needed
- prioritize readability 
- Each function or class method should do only one specific job. Instead of a single processData method that both validates and saves, you should have a validateData method and a separate saveData method. This makes your code easier to test, reuse, and reason about. Keep readability as the top priority and avoid over-modularizing.
- Be explicit: always define the types for function parameters and return values. Use specific types instead of any (or use interface where logical)
- Where a block of code is complex, use comments (//) to annotate the steps. Prefer simple, readable code over clever but confusing optimizations unless performance is a critical, stated requirement.
- Add constants at the top of the file for things that the user indicates they would like to change or are often repeated. Do not overdo this.
- No Emoji's
- NO OVERENGINEERING, NO FALLBACKS
- For not implemented features, throw an error, do not implement fallbacks or hardcode responses.
- Fail fast, throw errors immediately if values are not as expected.
- Create code sections MAIN HANDLERS / ENDPOINTS / MAIN ENTRYPOINTS / ... (depends on the situation), and HELPER FUNCTIONS. Put the MAIN HANDLERS (or equivalent) at the top of the file
- Add a description of what the file does. This should first be a short, human-readable summary to understand it, followed by a couple bullet points with the responsibilities



## Naming Conventions

- **Component files**: Use PascalCase (e.g., `MyComponent.tsx`)
- **Component names**: Use PascalCase (e.g., `const MyComponent = () => {...}`)
- **Props**: Use camelCase (e.g., `onClick`, `backgroundColor`)
- **Variable names**: Use camelCase (e.g., `userProfile`, `setIsLoading`)
- **Custom hooks**: Start with "use" (e.g., `useWindowSize`)


## Code sections example
// ============================================================================
// SECTION NAME
// ============================================================================

Please await your instructions



# PYTHON

## Formatting of Code Guide

You must format the code such that it is easy to read for a junior developer. Make sure to keep functionality the same, except if stated otherwise. Keep code simple, do not use fallbacks except if the user requests this, prefer raising errors in a simple way. Do not overcomplicate, simple is best.

## Code Guideliness
- Use Descriptive Names: Good code is readable. It uses clear, full names for functions and variables (calculate_rectangle_area) instead of short, cryptic ones (ca), so you know what it does without having to read the code itself.
- Write Single-Purpose Functions: Good code is modular. Each function should do only one specific job. Instead of a single process function that both cleans data and sums it, you have a clean_data function and a separate calculate_total function, making your code easier to test and reuse. BUT KEEP IN MIND: do not over-do this, readability always has priority. 
- Be Explicit with Type Hints: Good code is predictable. It uses type hints (like width: float) to specify what kind of data a function expects and what it returns. This prevents errors by making it clear how to use the function correctly, avoiding crashes like add_numbers(2, "3").
- Build Robust Code: Good code is resilient and doesn't crash easily. It anticipates potential problems, like receiving a number as a string ("3"), and handles them gracefully instead of throwing an error.
- Document Your Code: Good code is self-explanatory. It includes docstrings ("""...""") that describe what a function does, what its arguments are, and what it returns. This allows others to use your code without having to decipher its logic.
-  Code remains easy to read. Where less easy to read, comments annotate complicated sets of instructions. Prefer readability over performance, except if the user explicitely requests otherwise.
- for longer pieces of code, comment the code with "logical blocks" (eg. # Step 1: code does this # Step 2: code does this)
- section the python file using ### CONSTANTS ###, ### HELPER FUNCTIONS ###, etc
- only add constants for things that the user indicated they would like to change, or for things that are repeated. do not include a constant for every single thing that can be changed. 
- use simple language, avoid jargon
- NO FALLBACKS, KEEP IT SIMPLE
- methods that are only referenced inside the file should be precedded with an underscore (_)
- never use emoji's
- documentation should say what the current code does, not reference previous code
- use DTO pattern where appropriate
- Fail Fast! Throw an error if something is not right, do not continue with a default or a fallback.
- For not implemented features, throw an error, do not implement fallbacks or hardcode responses.



## Example sections
# ============================================================================
# SECTION NAME
# ============================================================================

Now, please await your instructions