#!/usr/bin/env fish
# Stop Local LLM Server

set GREEN '\033[0;32m'
set YELLOW '\033[1;33m'
set NC '\033[0m'

echo -e "${YELLOW}Stopping local LLM server...${NC}"

if test -f /tmp/rapid-mlx.pid
    set PID (cat /tmp/rapid-mlx.pid)
    
    if ps -p $PID >/dev/null 2>&1
        kill $PID 2>/dev/null
        sleep 2
        
        if ps -p $PID >/dev/null 2>&1
            kill -9 $PID 2>/dev/null
        end
        
        echo -e "${GREEN}✓${NC} Server stopped (PID: $PID)"
    else
        echo -e "${YELLOW}Server process not found${NC}"
    end
    
    rm /tmp/rapid-mlx.pid
else
    echo -e "${YELLOW}No PID file found${NC}"
    pkill -f "rapid-mlx serve" 2>/dev/null
    echo -e "${GREEN}✓${NC} Killed any remaining server processes"
end

rm -f /tmp/rapid-mlx.log
echo -e "${GREEN}Cleanup complete${NC}"
