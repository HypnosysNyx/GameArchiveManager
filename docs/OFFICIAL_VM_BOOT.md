# Official 0.1.0 VM boot — guestcontrol verified

Time: 2026-09-02T18:02:00+08:00

- VM: `Win11-Sandbox` was already running and was left running.
- Guest Additions are available and the guest user is `sandbox`.
- The formal package was copied with `guestcontrol copyto` using the workspace-local password-file reference `.vm_gate/guestcontrol.passwordfile`.
- Guest package: `C:\Users\sandbox\AppData\Local\Temp\GameArchiveManager-0.1.0.zip`
- Guest ZIP SHA-256: `0964FAA028F6507470C07056129C7E5014B8AD6D0FD492C238F0603CFCE60FFC`
- Guest EXE SHA-256: `62D404EAD9F21B8BC62D05CBADB22E82F15BD5D07CA694F6B2BDF3039ACD77D4`
- The extracted formal EXE reported version `0.1.0` and build identity `Release`.
- A single `Q` was sent through a guest-side PowerShell stdin pipeline to the formal EXE; it exited with code `0`.

Result: **PASS** — authenticated guestcontrol copy, guest hash verification, EXE identity capture, and redirected `Q` completed. No password value is recorded here. The VM was not shut down.
