# Frontend: build the React app, then serve it with nginx.
# nginx also forwards /api/* to the backend, so the browser only talks to one address.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# Where the backend lives. docker-compose and Azure each set this.
ENV BACKEND_URL=http://backend:8000
ENV PORT=80
EXPOSE 80
