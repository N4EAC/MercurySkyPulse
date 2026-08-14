# Using the Mercury SkyPulse BBS

The BBS works over an established Mercury ARQ connection. One station hosts its
local mailbox, bulletin, and file catalog; the connected station can exchange
content with it through the BBS tab.

## Callsign fields

- **Setup > User > Callsign** is the station's normal identity. Saving it fills
  Chat **My callsign** and BBS Access **Callsign** when those fields are empty.
  This is an initial convenience only: later edits are not overwritten.
- **Access > Callsign** identifies this station when authenticating to the
  connected station's protected BBS. It is not a separate BBS owner setting.
- **Access > Commander** establishes the administrator of this computer's local
  BBS when protection is enabled. The commander can unlock local security
  controls, disable protection, change the shared password, and assign roles.
  Commander administration is local-only and is not sent as a remote command.
- **Compose > From** and **Files > Owner callsign** identify submitted content.
  With protection enabled, they must match the callsign authenticated for the
  current ARQ session. In open mode they are not authenticated.

## Connect and use an open BBS

1. Enter the station callsign under **Setup > User** and save it.
2. MSP automatically listens for incoming ARQ connections whenever Mercury's TNC
   is ready; Chat shows the active listening identity. You may also connect to
   the other station from Chat.
3. Open BBS. When the remote BBS is unprotected, authentication is unnecessary.
4. Use **Compose** for private mail or bulletins. Use **Files** to publish or
   request catalog files. Private mail is addressed but is not encrypted.

## Protect the local BBS

1. Open **BBS > Access** on the computer hosting the BBS.
2. Enter the local administrator callsign in **Commander**, choose a password of
   10–256 characters, and select **Enable Protection**.
3. Unlock local controls with the commander password before changing protection
   or assigning roles.
4. Assign each permitted callsign a role:
   - `user`: private mail and file downloads.
   - `operator`: user permissions plus bulletin and file publication.
   - `commander`: operator permissions plus the commander authorization level.

The configured commander cannot be demoted. Although multiple callsigns can be
assigned the `commander` role, protection settings and role administration still
require the local password unlock on the host computer.

## Authenticate to a protected remote BBS

1. Establish the Mercury ARQ connection first.
2. Open **BBS > Access**. Confirm **Callsign** contains the identity assigned a
   role by the remote BBS commander.
3. Enter the remote BBS shared password and select **Authenticate to Connected
   BBS**.
4. Complete BBS operations while that ARQ session remains connected.

Authentication uses a fresh challenge and does not transmit or store the
plaintext password. It controls access but does not encrypt BBS traffic. A
disconnect clears the authenticated session.
