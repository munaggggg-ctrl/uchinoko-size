#!/bin/bash
# 初回セットアップは完了済みです。以後の更新は sync.command が行います。
exec "$(dirname "$0")/sync.command"
