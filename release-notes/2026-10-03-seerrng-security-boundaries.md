---
category: security
audience: users, operators
area: integration
action: none
breaking: false
---
SeerrNG can now use its own integration-only key. Concurrent submissions are deduplicated, request bodies and workers are bounded, and plugin operations stop when seccomp is unavailable unless an operator explicitly opts out.
