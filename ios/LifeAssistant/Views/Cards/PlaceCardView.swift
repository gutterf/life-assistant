import Foundation
import SwiftUI

/// 周边搜索结果卡片：名称、评分、距离
struct PlaceCardView: View {

    let card: ResultCard

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CardHeader(symbol: "fork.knife", title: card.title, subtitle: card.subtitle)

            Rectangle().fill(Palette.hairline).frame(height: 0.8)

            if card.places.isEmpty {
                Text("没有找到结果")
                    .font(Typeface.body(14))
                    .foregroundStyle(Palette.inkTertiary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 20)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(card.places.enumerated()), id: \.element.id) { index, place in
                        PlaceRow(rank: index + 1, place: place)
                        if index < card.places.count - 1 {
                            Rectangle()
                                .fill(Palette.hairline.opacity(0.7))
                                .frame(height: 0.7)
                                .padding(.leading, 34)
                        }
                    }
                }
            }
        }
    }
}

private struct PlaceRow: View {
    let rank: Int
    let place: PlaceItem

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            Text("\(rank)")
                .font(Typeface.metric(11, .bold))
                .foregroundStyle(rank <= 3 ? Palette.accentDeep : Palette.inkSecondary)
                .frame(width: 23, height: 23)
                .background(
                    Circle().fill(rank <= 3 ? Palette.accentSoft : Palette.canvasDeep)
                )

            VStack(alignment: .leading, spacing: 5) {
                Text(place.name)
                    .font(Typeface.body(15.5, .semibold))
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    if let rating = place.rating {
                        HStack(spacing: 3) {
                            Image(systemName: "star.fill")
                                .font(.system(size: 9))
                                .foregroundStyle(Color(red: 0.86, green: 0.63, blue: 0.16))
                            Text(String(format: "%.1f", rating))
                                .font(Typeface.metric(12, .semibold))
                                .foregroundStyle(Palette.inkSecondary)
                        }
                    }
                    if let category = place.category, !category.isEmpty {
                        Text(category)
                            .font(Typeface.body(11.5))
                            .foregroundStyle(Palette.inkTertiary)
                            .lineLimit(1)
                    }
                }

                if let address = place.address, !address.isEmpty {
                    Text(address)
                        .font(Typeface.body(12.5))
                        .foregroundStyle(Palette.inkSecondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: 6)

            VStack(alignment: .trailing, spacing: 4) {
                if let distance = place.distanceM {
                    Text(Format.distance(distance))
                        .font(Typeface.metric(13, .semibold))
                        .foregroundStyle(Palette.accentDeep)
                }
                if let phone = place.phone, !phone.isEmpty {
                    Text(phone)
                        .font(Typeface.metric(11))
                        .foregroundStyle(Palette.inkTertiary)
                }
            }
        }
        .padding(.vertical, 11)
    }
}
