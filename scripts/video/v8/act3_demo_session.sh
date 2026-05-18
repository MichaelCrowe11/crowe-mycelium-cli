#!/usr/bin/env bash
# Run by asciinema to capture a realistic Act 3 demo session.
# The output is recorded as a .cast file and replayed as video.

# Clear and pause briefly for visual reset
clear
sleep 0.5

# Show the user typing the command (simulated with a sleep + echo)
printf "$ "
sleep 1.5
typed="ollama run Mcrowe1210/gemma-4-mycelium-e4b"
for (( i=0; i<${#typed}; i++ )); do
  printf "%s" "${typed:$i:1}"
  sleep 0.04
done
printf "\n"

# Run the model with the contamination prompt
sleep 0.8
ollama run Mcrowe1210/gemma-4-mycelium-e4b \
  "why is my agar dish growing fuzzy green colonies near the edge but the center looks clean?"

sleep 1.5
printf "\n"
