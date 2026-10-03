---
category: security
audience: operators
area: containers
action: Configure MOONLIGHT_TLS_CA_FILE or MOONLIGHT_TLS_FINGERPRINT, or explicitly opt in to insecure TLS on a trusted LAN.
breaking: true
---
The Docker Compose example now uses a read-only root filesystem, drops unnecessary capabilities, and enables no-new-privileges. Sunshine connections require a trusted CA or certificate pin; published images also carry signed provenance and SPDX SBOM attestations.
