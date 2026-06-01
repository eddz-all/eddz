import SwiftUI

struct ContentView: View {
    @ObservedObject var store: ExecutorStore

    var body: some View {
        NavigationSplitView {
            List {
                Label("Connection", systemImage: "network")
                Label("Activity", systemImage: "waveform.path.ecg")
            }
            .listStyle(.sidebar)
            .navigationTitle("ProjectPilot")
        } detail: {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HeaderView(store: store)
                    ConnectionFormView(store: store)
                    StatusPanelView(store: store)
                }
                .padding(22)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(.background)
        }
    }
}

private struct HeaderView: View {
    @ObservedObject var store: ExecutorStore

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            Image(systemName: store.isRunning ? "checkmark.circle.fill" : "power.circle")
                .font(.system(size: 32))
                .foregroundStyle(store.isRunning ? .green : .secondary)

            VStack(alignment: .leading, spacing: 3) {
                Text("ProjectPilot Executor")
                    .font(.title2.bold())
                Text(store.isRunning ? "Connected and polling for approved tasks." : "Ready to connect to the backend.")
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}
