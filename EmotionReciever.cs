using UnityEngine;
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine.Video;
using System.Collections;

public class EmotionReceiver : MonoBehaviour
{
    public int port = 5005;           // Python UDP_PORT와 동일하게
    public string currentEmotion = "none";

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool running = false;

    public VideoPlayer videoPlayer; // videoPlayer 스크립트 참조

    public VideoClip happyClip;
    public VideoClip sadClip;
    public VideoClip angryClip;
    public VideoClip neutralClip;


    void Start()
    {
        udpClient = new UdpClient(port);
        running = true;

        receiveThread = new Thread(ReceiveData);
       // receiveThread.IsBackground = true;
        receiveThread.Start();

        Debug.Log("EmotionReceiver: UDP listening on port " + port);
        changeClip();
    }

string newEmotion = "";
    private void ReceiveData()
    {
        IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

        while (running)
        {
            try
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data).Trim();
                if (text == currentEmotion)
                    continue; // 동일한 감정이면 무시

                newEmotion = text;
   



                Debug.Log("Received emotion: " + text);
            }
            catch (Exception e)
            {
                Debug.Log("UDP Receive error: " + e.Message);
            }
        }
    }
    void FixedUpdate()  
    {
        if (newEmotion != "" && newEmotion != currentEmotion)
        {
            currentEmotion = newEmotion;
            changeClip(); 
        }
    }


    void changeClip()
    {
        
        VideoClip selectedClip = null;
        switch (currentEmotion)
        {
            case "happy":
                selectedClip = happyClip;
                break;
            case "sad":
                selectedClip = sadClip;
                break;
            case "angry":
                selectedClip = angryClip;
                break;
            case "neutral":
                selectedClip = neutralClip;
                break;
            default:
                selectedClip = neutralClip;
                Debug.Log("Unknown emotion: " + currentEmotion);
                break;
        }
        //if (selectedClip == videoPlayer.clip)
        //  return; // 이미 재생 중인 클립이면 변경하지 않음

        videoPlayer.clip = selectedClip;
        videoPlayer.Play();
        Debug.Log("Changed clip to emotion: " + currentEmotion);
    }


    void OnApplicationQuit()
    {
        running = false;

        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Abort();
        }

        if (udpClient != null)
        {
            udpClient.Close();
        }
    }
}
