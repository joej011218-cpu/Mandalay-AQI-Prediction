



      (function () {



        function renderHeaderClock() {



          var el = document.getElementById("liveClock");



          if (!el) return;



          var now = new Date();



          var timeText = now.toLocaleTimeString("en-US", {



            timeZone: "Asia/Yangon",
            hour: "numeric",



            minute: "2-digit",



            second: "2-digit",



            hour12: true



          });



          var dateText = now.toLocaleDateString("en-US", {



            timeZone: "Asia/Yangon",
            weekday: "short",



            month: "short",



            day: "numeric",



            year: "numeric"



          });



          el.innerHTML = '<span class="clock-time">' + timeText + '</span>' +



                         '<span class="clock-date">' + dateText + '</span>';



        }







        renderHeaderClock();



        window.setInterval(renderHeaderClock, 1000);



        document.addEventListener("visibilitychange", function () {



          if (!document.hidden) renderHeaderClock();



        });



        window.addEventListener("focus", renderHeaderClock);



      })();



      