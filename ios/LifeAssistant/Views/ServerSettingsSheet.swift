import SwiftUI

/// 连接设置：填写后端地址并现场测通，装到手机后改 IP 不必重新编译。
struct ServerSettingsSheet: View {

 @Bindable var vm: ChatViewModel
 @Environment(\.dismiss) private var dismiss

 // 模型与密钥：改动立即生效，无需点保存
 @State private var modelPreset: ModelPreset = ServerSettings.modelPreset
 @State private var customModelName: String = ServerSettings.customModelName
 @State private var apiKey: String = ServerSettings.apiKey

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
 Picker("模型", selection: $modelPreset) {
 ForEach(ModelPreset.allCases) { preset in
 Text(preset.label).tag(preset)
 }
 }
 .font(Typeface.metric(15))
 .onChange(of: modelPreset) { _, newValue in
 ServerSettings.modelPreset = newValue
 }

 if modelPreset == .custom {
 TextField("模型名，例如 deepseek-chat", text: $customModelName)
 .textInputAutocapitalization(.never)
 .autocorrectionDisabled()
 .font(Typeface.metric(15))
 .onChange(of: customModelName) { _, newValue in
 ServerSettings.customModelName = newValue
 }
 }

 SecureField("API Key（留空用服务器端的 key）", text: $apiKey)
 .textInputAutocapitalization(.never)
 .autocorrectionDisabled()
 .font(Typeface.metric(15))
 .onChange(of: apiKey) { _, newValue in
 ServerSettings.apiKey = newValue
 }
 } header: {
 Text("模型与密钥")
 } footer: {
 Text("模型选择与 API Key 只存在这台设备上，随每次请求发送给后端，"
 + "优先于服务器上的默认配置。留空则用服务器配置。改完立即生效。")
 }

 Section {
 LabeledContent("当前地址", value: ServerSettings.rawValue)
 .font(Typeface.metric(13))
 LabeledContent("生效模型", value: ServerSettings.effectiveModel)
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
