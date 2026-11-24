# Receiver

Read [the project brief](../README.md), [the protocol](../CONTRACT.md), [agent coordination](../TEAM.md) and [decisions](../04-demo/DECISIONS.md). Start from the [reference packet](../fixtures/packet-v1.json).

Build the OpenCV command-line video decoder. Implement manual ROI, frame luminance extraction, time-base handling, preamble search, payload recovery and CRC. Begin with a synthetic time series built from the reference bits, then test the first physical clip. Hand off JSON output, commands and decoder limitations to Integration.

Write within this folder. Read sibling outboxes when starting, when blocked and before handoff. Post progress, requests and reproducible verification to [STATUS.md](STATUS.md).
