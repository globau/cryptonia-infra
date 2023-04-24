FROM alpine

RUN apk update && \
    apk upgrade && \
    apk add openjdk17 busybox-extras

RUN addgroup -g 1000 minecraft && \
    adduser -D -u 1000 -G minecraft minecraft -h /minecraft

USER minecraft

STOPSIGNAL SIGINT
WORKDIR /minecraft
CMD ["java", "-Xmx512M", "-Xms512M", "-jar", "BungeeCord.jar"]
