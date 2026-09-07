add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), geolocation=(), microphone=()" always;
add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; frame-src 'self'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'; frame-ancestors 'self'; form-action 'self'" always;
