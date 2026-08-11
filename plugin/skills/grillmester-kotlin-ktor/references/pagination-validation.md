# Pagination and request validation in Ktor

## Follow the existing contract

Inspect list routes, query parsing, DTOs, database pagination, ordering, error
responses, tests, and published API documentation. Determine whether the API
uses offset, page number, cursor, continuation token, or no pagination. Do not
change parameter names, indexing origin, default size, maximum size, ordering,
or response metadata without treating it as a contract change.

## Choose a stable pagination model

- Offset or page pagination is simple for small, mostly stable result sets but
  can skip or duplicate records while data changes.
- Cursor pagination is better for large or changing sets when it uses a stable,
  deterministic ordering with a unique tie-breaker.
- Always bound the page size and define deterministic ordering.
- Do not expose sensitive database keys in an unsigned cursor. Use an opaque,
  validated token when cursor contents require integrity or confidentiality.

An offset-style route can validate at the boundary:

```kotlin
@Serializable
data class PageResponse<T>(
    val items: List<T>,
    val page: Int,
    val pageSize: Int,
    val total: Long? = null,
)

get("/api/resources") {
    val pageInput = call.request.queryParameters["page"]
    val pageSizeInput = call.request.queryParameters["page_size"]
    val page = pageInput?.toIntOrNull()
        ?: if (pageInput == null) 0 else throw ApiFailure.InvalidInput("Invalid page")
    val pageSize = pageSizeInput?.toIntOrNull()
        ?: if (pageSizeInput == null) defaultPageSize
        else throw ApiFailure.InvalidInput("Invalid page size")

    if (page < 0 || pageSize !in 1..maximumPageSize) {
        throw ApiFailure.InvalidInput("Invalid pagination parameters")
    }

    call.respond(repository.findPage(page, pageSize))
}
```

Defaults, parameter names, route, response fields, and failure type are
illustrative. Derive them from the repository or agree a new API contract.
Avoid `page * pageSize` overflow and unbounded count queries.

## Validate requests in layers

1. Let content negotiation reject malformed syntax.
2. Validate structural constraints at the route or DTO boundary: required
   values, ranges, lengths, formats, and mutually exclusive fields.
3. Validate domain invariants in application or domain code so non-HTTP callers
   receive the same protection.
4. Enforce authorization after deriving identity from the validated token, not
   from an identity supplied in the body or query.
5. Enforce database constraints for invariants that must remain true under
   concurrency.

Return stable error codes and safe messages. Never echo a body, national
identity number, token, or sensitive query value into a response or log.

## Tests

Cover defaults, minimum and maximum bounds, invalid numbers, overflow, empty and
last pages, stable ordering, concurrent inserts where relevant, invalid or
tampered cursors, domain validation, authorization, and contract serialization.
For database-backed pagination, verify the generated query has a deterministic
order and bounded result set.
