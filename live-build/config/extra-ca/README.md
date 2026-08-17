# Extra / enterprise CAs

If your network intercepts HTTPS (a TLS-inspecting firewall or proxy), the build
can't verify vendor download servers with the standard CA bundle. Drop the
interceptor's **root CA** here as a `.crt` (PEM) file and `build.sh` will trust it
before fetching keys.

Capture the CA your network presents (only do this if you TRUST your network):

    openssl s_client -connect download.docker.com:443 -showcerts </dev/null 2>/dev/null \
      | awk '/-----BEGIN CERTIFICATE-----/{n++} n{print > "/dev/stdout"}' \
      | csplit -sz -f cert- -b '%02d.crt' /dev/stdin '/-----BEGIN CERTIFICATE-----/' '{*}' 2>/dev/null || true
    # the LAST cert-NN.crt is the network's root — copy it here:
    cp "$(ls cert-*.crt | tail -1)" network-proxy.crt

Then re-run build.sh.
