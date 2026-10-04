import SwiftUI

/// 连接设置：填写后端地址并现场测通，装到手机后改 IP 不必重新编译。
struct ServerSettingsSheet: View {

    @Bindable var vm: ChatViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://192.168.1.20:8000", text: $vm.serverAddressDraft)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .font(Typeface.metric(15))
                } header: {
                    Text("后端地址")
                } footer: {
                    Text("真机必须填电脑的局域网 IP，不能填 127.0.0.1——那指向手机自己。"
                         + "可省略 http:// 前缀。改完点保存，无需重新安装 App。")
                }

                Section {
                    Button {
                        vm.saveServerAddress()
                    } label: {
                        HStack {
                            Text("保存并测试连接")
                            Spacer()
                            if vm.isCheckingServer {
                                ProgressView().controlSize(.small)
                            }
                        }
                    }
                    .disabled(vm.isCheckingServer)

                    Button("恢复默认地址") { vm.resetServerAddress() }
                        .foregroundStyle(Palette.inkSecondary)
                }

                if let result = vm.serverCheckResult {
                    Section {
                        Text(result)
                            .font(Typeface.body(14))
                            .foregroundStyle(result.hasPrefix("连接失败") ? Palette.accentDeep : Palette.ink)
                    }
                }

                Section {
                    LabeledContent("当前地址", value: ServerSettings.rawValue)
                        .font(Typeface.metric(13))
                }
            }
            .navigationTitle("连接设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                        .fontWeight(.semibold)
                }
            }
        }
        .task {
            // 打开设置页就自动测一次，省得用户还要自己点
            if vm.serverCheckResult == nil {
                await vm.testServerConnection()
            }
        }
    }
}
