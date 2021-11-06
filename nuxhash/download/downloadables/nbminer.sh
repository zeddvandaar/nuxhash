#!/bin/sh

VERSION='39.5'
SHA256='c9743b2cd3b3691fe6fd1e65944da934cfb2b86e7814d20eb72a24bab8e868a5'

case "$1" in
verify)
        [ -f nbminer ] && [ `sha256sum nbminer | awk '{print $1}'` = "$SHA256" ]
        exit $?
        ;;
download)
        curl -L -O "https://github.com/NebuTech/NBMiner/releases/download/v${VERSION}/NBMiner_${VERSION}_Linux.tgz"
        mv "NBMiner_${VERSION}_Linux.tgz" data.tgz
        tar xf data.tgz --strip-components 1 --wildcards NBMiner_Linux/*
        rm -f data.tgz
        exit 0
        ;;
esac

