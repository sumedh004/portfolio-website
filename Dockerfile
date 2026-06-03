FROM nginx:1.25-alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy your site files into the nginx serving directory
COPY index.html /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/
COPY assets/ /usr/share/nginx/html/assets/

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx listens on port 80 inside the container
EXPOSE 80

# Default nginx command (already set in the base image, but explicit is good)
CMD ["nginx", "-g", "daemon off;"]
