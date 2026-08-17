# Sysible Server is an engineering/admin server — expose the sbin dirs
# (ifconfig, route, ethtool, etc.) on every user's PATH.
case ":$PATH:" in
    *:/usr/sbin:*) ;;
    *) PATH="/usr/local/sbin:/usr/sbin:/sbin:$PATH"; export PATH ;;
esac
