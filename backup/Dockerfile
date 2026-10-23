FROM alpine:3.20
RUN apk add --no-cache postgresql16-client aws-cli tar bash coreutils
COPY sauvegarde.sh restauration.sh boucle.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
CMD ["boucle.sh"]
