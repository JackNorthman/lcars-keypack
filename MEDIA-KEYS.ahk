; LCARS media keys for Keyboard Sounds Pro -- AutoHotkey v2.
;
; Pro's key table (backend/key/key_windows.go, 114 keys, VK 0x08-0xDE) has NO
; media or volume keys, so they can never be mapped in a profile -- not via the
; editor, not by hand-editing the YAML. F13-F24 ARE in the table and nothing
; uses them by default.
;
; So: set your macropad (or remapping tool) to send F13-F18 instead of the media
; keys, let Keyboard Sounds Pro play the LCARS sound for those keys (lcars-plus
; already maps them), and let this script issue the real media command.

F13::Send "{Volume_Up}"
F14::Send "{Volume_Down}"
F15::Send "{Volume_Mute}"
F16::Send "{Media_Prev}"
F17::Send "{Media_Play_Pause}"
F18::Send "{Media_Next}"
