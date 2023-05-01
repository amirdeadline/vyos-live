sla_profile=$1

if /bin/cli-shell-api listNodes sdwan sla-profiles | grep -q "\<$sla_profile\>"; then
    exit 0
else
    exit 1
fi
