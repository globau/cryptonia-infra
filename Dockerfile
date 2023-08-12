FROM alpine

RUN apk update && \
    apk upgrade && \
    apk add --no-cache openjdk17 busybox-extras libstdc++

RUN addgroup -g 1000 minecraft && \
    adduser -D -u 1000 -G minecraft minecraft -h /minecraft

USER minecraft

STOPSIGNAL SIGINT
WORKDIR /minecraft
