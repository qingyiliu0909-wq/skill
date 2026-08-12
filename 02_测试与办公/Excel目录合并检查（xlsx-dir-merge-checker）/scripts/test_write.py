import os

# Simple test
output_path = os.path.join(os.path.dirname(__file__), "test_output.txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write("Hello, World!\n")
    f.write("Test successful\n")

print(f"Test file created at: {output_path}")