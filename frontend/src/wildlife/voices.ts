import penguin from "../../assets/audio/penguin.mp3";
import kakapo from "../../assets/audio/kakapo.mp3";
import elephant from "../../assets/audio/elephant.mp3";
import panda from "../../assets/audio/panda.mp3";
import whale from "../../assets/audio/whale.mp3";

export const voices: Record<string, { src: string; credit: string; source: string } | undefined> = {
  penguin: {
    src: penguin,
    credit: "Favaro, Gamba, Alfieri, Pessani & McElligott / CC BY 4.0",
    source:
      "https://commons.wikimedia.org/wiki/File:Vocal-individuality-cues-in-the-African-penguin-(Spheniscus-demersus)-a-source-filter-theory-srep17255-s2.oga",
  },
  kakapo: {
    src: kakapo,
    credit: "Department of Conservation, NZ / CC BY 4.0",
    source: "https://commons.wikimedia.org/wiki/File:Kakapo-18.wav",
  },
  elephant: {
    src: elephant,
    credit: "தகவலுழவன் / CC0",
    source: "https://commons.wikimedia.org/wiki/File:Elephant_voice_-_trumpeting.ogg",
  },
  panda: {
    src: panda,
    credit: "Attributed to Mizunoryu / public domain",
    source: "https://commons.wikimedia.org/wiki/File:Red_panda_twittering.ogg",
  },
  whale: {
    src: whale,
    credit: "NOAA / CC0",
    source: "https://commons.wikimedia.org/wiki/File:Blue_Whale_NE_Pacific_1x.oga",
  },
};
