// A deterministic macOS sensor. No model calls or input injection.
import Cocoa
import ApplicationServices
import Vision

func ax(_ element: AXUIElement, _ attribute: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, attribute, &value) == .success ? value : nil
}
func strings(_ root: AXUIElement) -> [String] {
    var queue = [root], result = [String](), seen = Set<String>(), visited = 0
    while !queue.isEmpty && visited < 350 && result.joined().count < 30000 {
        let node = queue.removeFirst(); visited += 1
        if ax(node, kAXSubroleAttribute as CFString) as? String == "AXSecureTextField" {
            continue
        }
        for key in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] {
            if let value = ax(node, key as CFString) as? String,
               !value.isEmpty, seen.insert(value).inserted {
                result.append(String(value.prefix(4000)))
            }
        }
        if let children = ax(node, kAXChildrenAttribute as CFString) as? [AXUIElement] {
            queue.append(contentsOf: children.prefix(80))
        }
    }
    return result
}
var output: [String: Any] = [
    "screen_permission": CGPreflightScreenCaptureAccess(),
    "accessibility_permission": AXIsProcessTrusted(),
    "idle_seconds": CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .null)
]
let session = CGSessionCopyCurrentDictionary() as? [String: Any] ?? [:]
let locked = session["CGSSessionScreenIsLocked"] as? Bool ?? false
output["screen_locked"] = locked
if let app = NSWorkspace.shared.frontmostApplication, !locked {
    output["app"] = app.localizedName ?? ""
    output["bundle_id"] = app.bundleIdentifier ?? ""
    output["pid"] = app.processIdentifier
    let element = AXUIElementCreateApplication(app.processIdentifier)
    AXUIElementSetMessagingTimeout(element, 0.5)
    if let window = ax(element, kAXFocusedWindowAttribute as CFString) {
        let node = unsafeBitCast(window, to: AXUIElement.self)
        output["window"] = ax(node, kAXTitleAttribute as CFString) as? String ?? ""
        output["accessibility_text"] = strings(node)
    }
}
if CommandLine.arguments.count > 1 && !locked {
    let directory = URL(fileURLWithPath: CommandLine.arguments[1])
    var displayCount: UInt32 = 0
    CGGetActiveDisplayList(0, nil, &displayCount)
    var screens = [[String: Any]]()
    for index in 1...max(1, Int(displayCount)) {
        let file = directory.appendingPathComponent("display-\(index).jpg")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = ["-x", "-t", "jpg", "-D", String(index), file.path]
        let errors = Pipe(); process.standardError = errors
        do {
            try process.run(); process.waitUntilExit()
            var screen: [String: Any] = ["display": index, "file": file.lastPathComponent]
            if process.terminationStatus == 0 && FileManager.default.fileExists(atPath: file.path) {
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.usesLanguageCorrection = false
                request.automaticallyDetectsLanguage = true
                do {
                    try VNImageRequestHandler(url: file).perform([request])
                    screen["text"] = request.results?.compactMap { $0.topCandidates(1).first?.string } ?? []
                } catch { screen["ocr_error"] = String(describing: error) }
            } else {
                screen["capture_error"] = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "capture failed"
            }
            screens.append(screen)
        } catch { screens.append(["display": index, "capture_error": String(describing: error)]) }
    }
    output["screens"] = screens
}
let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
