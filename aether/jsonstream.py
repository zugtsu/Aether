_SIMPLE = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class SayStream:
    def __init__(self, key="say"):
        self.marker = f'"{key}"'
        self.buf = ""
        self.pos = 0
        self.state = "seek"
        self.pending_high = None
        self.text = ""

    def feed(self, chunk):
        self.buf += chunk
        out = []
        b = self.buf
        while self.pos < len(b) and self.state != "done":
            if self.state == "seek":
                i = b.find(self.marker, self.pos)
                if i == -1:
                    self.pos = max(self.pos, len(b) - len(self.marker))
                    break
                self.pos = i + len(self.marker)
                self.state = "colon"
            elif self.state in ("colon", "quote"):
                c = b[self.pos]
                if c.isspace():
                    self.pos += 1
                elif self.state == "colon" and c == ":":
                    self.pos += 1
                    self.state = "quote"
                elif self.state == "quote" and c == '"':
                    self.pos += 1
                    self.state = "text"
                else:
                    self.state = "seek"
            else:
                c = b[self.pos]
                if c == '"':
                    self.pos += 1
                    self.state = "done"
                elif c == "\\":
                    if self.pos + 1 >= len(b):
                        break
                    e = b[self.pos + 1]
                    if e == "u":
                        if self.pos + 6 > len(b):
                            break
                        code = int(b[self.pos + 2:self.pos + 6], 16)
                        self.pos += 6
                        if 0xD800 <= code < 0xDC00:
                            self.pending_high = code
                            continue
                        if 0xDC00 <= code < 0xE000 and self.pending_high is not None:
                            code = 0x10000 + ((self.pending_high - 0xD800) << 10) + (code - 0xDC00)
                        self.pending_high = None
                        out.append(chr(code))
                    else:
                        out.append(_SIMPLE.get(e, e))
                        self.pos += 2
                else:
                    out.append(c)
                    self.pos += 1
        new = "".join(out)
        self.text += new
        return new
