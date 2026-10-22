import io

p = "static/style.css"
css = io.open(p, encoding="utf-8").read()

if "UPDATE 16" in css:
    print("UPDATE 16 already installed - nothing to do.")
else:
    css = css + """

/* ===== UPDATE 16: ad video clarity fix ===== */
/* remove the gold glow that was fogging the video */
.hero::after {
    display: none;
}
/* restore the original banner height */
.hero {
    padding: 130px 20px;
}
"""
    io.open(p, "w", encoding="utf-8", newline="").write(css)
    print("UPDATE 16 installed.")
    print("Gold glow removed - the video will look clear again.")
    print("Banner height restored to the original size.")

print("")
print("Now reboot: press Ctrl+C on the server terminal, then run:  python app.py")
print("Then refresh the browser with Ctrl+F5.")
