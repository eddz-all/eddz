import SwiftUI

struct StatusPanelView: View {
    @ObservedObject var store: ExecutorStore

    var body: some View {
        Grid(alignment: .topLeading, horizontalSpacing: 16, verticalSpacing: 16) {
            GridRow {
                GroupBox("Status") {
                    VStack(alignment: .leading, spacing: 10) {
                        LabeledContent("State") {
                            Text(store.isRunning ? "Running" : "Stopped")
                                .foregroundStyle(store.isRunning ? .green : .secondary)
                                .fontWeight(.semibold)
                        }
                        LabeledContent("Config") {
                            Text(store.hasSavedConfiguration ? AppPaths.configURL.path : "Not saved")
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        LabeledContent("Backend") {
                            Text(store.configuration.serverURL.isEmpty ? "-" : store.configuration.serverURL)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        LabeledContent("Last error") {
                            Text(store.lastError ?? "-")
                                .foregroundStyle(store.lastError == nil ? Color.secondary : Color.red)
                                .lineLimit(2)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Last Result") {
                    ScrollView {
                        Text(store.pollResult)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 150)
                }
            }

            GridRow {
                GroupBox("Executor Output") {
                    ScrollView {
                        Text(store.output.isEmpty ? "No output yet." : store.output)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 170)
                }
                .gridCellColumns(2)
            }
        }
    }
}
