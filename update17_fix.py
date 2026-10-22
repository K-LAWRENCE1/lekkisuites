import io

p = "static/style.css"
css = io.open(p, encoding="utf-8").read()

if "UPDATE 17" in css:
    print("UPDATE 17 already installed - nothing to do.")
else:
    css = css + """

/* ===== UPDATE 17: exact before look ===== */
.hero-divider {
    display: none;
}
.hero h1, .hero-content h1 {
    font-size: 60px;
}
"""
    io.open(p, "w", encoding="utf-8", newline="").write(css)
    print("UPDATE 17 installed.")
    print("Divider hidden, title back to the original size.")

print("")
print("Reboot: Ctrl+C on the server terminal, then:  python app.py")
print("Then refresh the browser with Ctrl+F5.")
