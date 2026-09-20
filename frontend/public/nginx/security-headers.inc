add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), geolocation=(), microphone=()" always;
add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; connect-src 'none'; font-src 'self'; frame-src 'none'; img-src 'self' data:; object-src 'none'; script-src 'none'; style-src 'self'; frame-ancestors 'none'; form-action 'none'" always;
