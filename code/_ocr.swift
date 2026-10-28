// OCR images with Apple Vision. Usage: swift _ocr.swift img1.png img2.png ...
// Prints JSON: { "<path>": [ { "text": "...", "h": <line height 0-1>, "y": <top 0-1> } ] }
import Foundation
import Vision
import AppKit

var result: [String: [[String: Any]]] = [:]
for path in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOfFile: path),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([request])
    var lines: [[String: Any]] = []
    for obs in request.results ?? [] {
        guard let top = obs.topCandidates(1).first else { continue }
        let box = obs.boundingBox
        lines.append(["text": top.string, "h": Double(box.height), "y": Double(1 - box.maxY)])
    }
    result[path] = lines
}
let data = try JSONSerialization.data(withJSONObject: result, options: [])
print(String(data: data, encoding: .utf8) ?? "{}")
