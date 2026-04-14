FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
ARG VITE_DEMO_TRAFFIC_TOKEN=
ENV VITE_DEMO_TRAFFIC_TOKEN=$VITE_DEMO_TRAFFIC_TOKEN
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
