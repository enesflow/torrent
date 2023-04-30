import WebTorrent from "webtorrent";

const client = new WebTorrent();
const magnetURI = "...";

client.add(magnetURI, (torrent) => {
	// Got torrent metadata!
	console.log("Client is downloading:", torrent.infoHash);

	for (const file of torrent.files) {
		document.body.append(file.name);
	}
});
