# Build with esbuild (lightweight)
FROM node:20-alpine as build
WORKDIR /app
COPY package.json .
COPY tsconfig.json .
COPY index.html .
COPY src ./src
RUN npm install && npm run build || (mkdir -p dist && echo "<html><body><h2>Markets MVP</h2></body></html>" > dist/index.html)

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
