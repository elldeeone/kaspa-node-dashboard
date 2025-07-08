FROM nginx:1.27.4-alpine

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the web dashboard files
COPY index.html custom.css dashboard.js kaspa-glow.png /usr/share/nginx/html/

# Expose port 8080
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"] 